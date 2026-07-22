#!/usr/bin/env python3
"""Three-finger drag daemon for Xorg and Wayland — macOS-style.

Passive mode (Xorg): the touchpad is left alone — events flow directly
to the display server with zero added latency. The daemon only watches
finger positions and injects the drag through a virtual mouse.

Proxy mode (Wayland): GNOME's built-in 3-finger workspace swipe cannot
be disabled, so the daemon exclusively grabs the touchpad and mirrors
its events to a uinput clone the compositor reads instead. The mirror
pauses while a gesture is in progress, hiding it from the desktop, and
the drag is injected as in passive mode.

Drag model (matches macOS):
  - 3 fingers down + movement (or a deliberate stationary hold) starts
    the drag; a still 3-finger tap does nothing.
  - Once dragging, the drag continues with however many fingers remain
    on the pad (1, 2 or 3) — lifting fingers mid-drag never hands the
    pointer back mid-gesture.
  - The drag ends a moment after ALL fingers lift (drag lock: touching
    again within the window resumes the same drag).
"""

import fcntl
import glob
import os
import select
import signal
import struct
import sys
import time

import evdev
from evdev import UInput, ecodes

# --- tuning ---------------------------------------------------------------
# macOS-style analog acceleration: pointer gain scales smoothly with
# finger velocity instead of a hard two-step switch.
#   gain = BASE_GAIN * (1 + (v / GAIN_REF_SPEED) ** GAIN_EXPONENT)
# v is centroid speed in touchpad units/s (bcm5974: ~97 units per mm).
BASE_GAIN = 0.13          # gain at near-zero speed: slow finger = precision
GAIN_REF_SPEED = 3500.0   # units/s where gain has roughly doubled
GAIN_EXPONENT = 1.1       # curve steepness
MAX_GAIN = 0.55           # cap so flicks stay controllable
VELOCITY_SMOOTHING = 0.5  # EMA factor for velocity (jitter suppression)

DRAG_START_DISTANCE = 20  # units (~0.2 mm) of motion before button press —
                          # a still 3-finger tap never fires a stray click
DRAG_START_HOLD = 0.25    # s of deliberate stationary hold also grabs
DRAG_RELEASE_DELAY = 0.25 # s after all fingers lift before the drag ends
RESYNC_GRACE = 0.08       # s to wait before re-showing leftover fingers to
                          # the compositor — a staggered 3-finger lift would
                          # otherwise read as a quick 2-finger tap (ghost
                          # right-click)
JUMP_GUARD = 150          # units: reject centroid teleports (finger clipping
                          # at the touchpad edge) beyond expected motion
# --------------------------------------------------------------------------

VIRTUAL_TAG = 'three-finger-drag'

# struct input_event on 64-bit: struct timeval (2 longs) + type, code, value.
EVENT_STRUCT = struct.Struct('llHHi')

TOOL_BITS = {
    1: ecodes.BTN_TOOL_FINGER,
    2: ecodes.BTN_TOOL_DOUBLETAP,
    3: ecodes.BTN_TOOL_TRIPLETAP,
    4: ecodes.BTN_TOOL_QUADTAP,
    5: ecodes.BTN_TOOL_QUINTTAP,
}

BUTTON_CODES = (ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE)


def find_touchpad():
    for path in sorted(glob.glob('/dev/input/event*')):
        try:
            dev = evdev.InputDevice(path)
        except (PermissionError, OSError):
            continue
        if VIRTUAL_TAG in dev.name:
            dev.close()
            continue
        caps = dev.capabilities()
        abs_codes = [c[0] if isinstance(c, tuple) else c
                     for c in caps.get(ecodes.EV_ABS, [])]
        if (ecodes.ABS_MT_POSITION_X in abs_codes
                and ecodes.ABS_MT_POSITION_Y in abs_codes):
            return dev
        dev.close()
    return None


def wayland_session_present():
    runtime_dir = os.environ.get('XDG_RUNTIME_DIR')
    if not runtime_dir:
        return False
    return bool(glob.glob(os.path.join(runtime_dir, 'wayland-*')))


def single_instance_lock():
    path = os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'),
                        'three-finger-drag.lock')
    lock = open(path, 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print('Another instance is already running', file=sys.stderr)
        sys.exit(0)
    return lock


def main():
    lock = single_instance_lock()

    touchpad = find_touchpad()
    if not touchpad:
        print('No touchpad found', file=sys.stderr)
        sys.exit(1)
    print(f'Touchpad: {touchpad.name} ({touchpad.path})')

    proxy_mode = wayland_session_present()

    mouse = UInput(
        {ecodes.EV_KEY: [ecodes.BTN_LEFT],
         ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y]},
        name=f'{VIRTUAL_TAG} virtual mouse')

    clone = None
    if proxy_mode:
        # Inherit the real device's identity (vendor/product/bus) so
        # libinput applies the same hardware quirks to the clone — e.g.
        # Apple touchpads' AttrTouchSizeRange, which filters out light
        # hover touches. Without this the clone gets generic handling
        # and the cursor jitters from barely-there contacts.
        clone = UInput.from_device(
            touchpad,
            name=f'{touchpad.name} {VIRTUAL_TAG} proxy',
            vendor=touchpad.info.vendor,
            product=touchpad.info.product,
            version=touchpad.info.version,
            bustype=touchpad.info.bustype,
            input_props=touchpad.input_props())
        touchpad.grab()

    slots = {}            # real device state: slot -> {abs_code: value}
    btn_state = {}        # real device state: button code -> 0/1
    clone_slots = set()   # slots the clone currently believes are down
    clone_btn = {}        # button state the clone currently believes
    clone_count = 0
    current_slot = 0
    frame_buf = bytearray()
    suppressed = False
    resync_at = None      # deferred-resync deadline (monotonic) or None
    dragging = False
    drag_n = 0            # finger count the drag is currently tracking
    pending = False       # 3 fingers down, button not yet pressed
    pend_t = 0.0
    cum_dist = 0.0
    prev_centroid = None
    prev_t = 0.0
    v_ema = 0.0
    release_time = None
    res_x = res_y = 0.0
    next_tid = 1

    def start_drag(n):
        nonlocal pending, dragging, drag_n, res_x, res_y
        pending = False
        dragging = True
        drag_n = n
        res_x = res_y = 0.0
        mouse.write(ecodes.EV_KEY, ecodes.BTN_LEFT, 1)
        mouse.syn()

    def end_drag():
        nonlocal dragging, pending, prev_centroid, release_time
        nonlocal v_ema, res_x, res_y
        if dragging:
            mouse.write(ecodes.EV_KEY, ecodes.BTN_LEFT, 0)
            mouse.syn()
        dragging = False
        pending = False
        prev_centroid = None
        v_ema = 0.0
        res_x = res_y = 0.0
        release_time = None

    def cleanup(*_args):
        end_drag()
        if proxy_mode:
            try:
                touchpad.ungrab()
            except OSError:
                pass
        touchpad.close()
        if clone is not None:
            clone.close()
        mouse.close()
        lock.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    def resync_clone():
        # After a suppression window the clone's picture is stale.
        # Frame 1 lifts everything it still holds; frame 2 places the
        # fingers that are really down right now with fresh tracking ids
        # and reconciles physical button state (a click released while
        # suppressed would otherwise leave the clone's button stuck).
        nonlocal clone_count, next_tid
        if clone_slots:
            for s in clone_slots:
                clone.write(ecodes.EV_ABS, ecodes.ABS_MT_SLOT, s)
                clone.write(ecodes.EV_ABS, ecodes.ABS_MT_TRACKING_ID, -1)
            if clone_count in TOOL_BITS:
                clone.write(ecodes.EV_KEY, TOOL_BITS[clone_count], 0)
            clone.write(ecodes.EV_KEY, ecodes.BTN_TOUCH, 0)
            clone.syn()
            clone_slots.clear()
            clone_count = 0
        wrote = False
        if slots:
            for s, axes in slots.items():
                clone.write(ecodes.EV_ABS, ecodes.ABS_MT_SLOT, s)
                clone.write(ecodes.EV_ABS, ecodes.ABS_MT_TRACKING_ID, next_tid)
                next_tid = next_tid % 65535 + 1
                for code, value in axes.items():
                    clone.write(ecodes.EV_ABS, code, value)
            first = next(iter(slots.values()))
            clone.write(ecodes.EV_ABS, ecodes.ABS_X,
                        first.get(ecodes.ABS_MT_POSITION_X, 0))
            clone.write(ecodes.EV_ABS, ecodes.ABS_Y,
                        first.get(ecodes.ABS_MT_POSITION_Y, 0))
            clone.write(ecodes.EV_KEY, ecodes.BTN_TOUCH, 1)
            if len(slots) in TOOL_BITS:
                clone.write(ecodes.EV_KEY, TOOL_BITS[len(slots)], 1)
            clone_slots.update(slots.keys())
            clone_count = len(slots)
            wrote = True
        for code, value in btn_state.items():
            if clone_btn.get(code, 0) != value:
                clone.write(ecodes.EV_KEY, code, value)
                clone_btn[code] = value
                wrote = True
        if wrote:
            clone.syn()

    def finish_drag():
        nonlocal suppressed, resync_at
        end_drag()
        if proxy_mode and suppressed:
            suppressed = False
            resync_at = None
            resync_clone()

    def drag_motion(cx, cy, t, n):
        # Continue the drag using the centroid of however many fingers
        # remain. Re-anchor on finger-count changes (the centroid jumps
        # when a finger joins/leaves) and on teleports (finger clipping
        # at the touchpad edges) — both would otherwise be a visible jerk.
        nonlocal prev_centroid, prev_t, v_ema, res_x, res_y, drag_n
        if prev_centroid is None or n != drag_n:
            drag_n = n
            prev_centroid = (cx, cy)
            prev_t = t
            return
        raw_dx = cx - prev_centroid[0]
        raw_dy = cy - prev_centroid[1]
        mag = (raw_dx ** 2 + raw_dy ** 2) ** 0.5
        dt = min(max(t - prev_t, 0.002), 0.05)
        if mag > v_ema * dt * 4 + JUMP_GUARD:
            prev_centroid = (cx, cy)
            prev_t = t
            return
        v = mag / dt
        v_ema = (VELOCITY_SMOOTHING * v
                 + (1 - VELOCITY_SMOOTHING) * v_ema)
        gain = min(MAX_GAIN, BASE_GAIN * (
            1 + (v_ema / GAIN_REF_SPEED) ** GAIN_EXPONENT))
        fx = raw_dx * gain + res_x
        fy = raw_dy * gain + res_y
        dx, dy = int(fx), int(fy)
        res_x, res_y = fx - dx, fy - dy
        if dx or dy:
            mouse.write(ecodes.EV_REL, ecodes.REL_X, dx)
            mouse.write(ecodes.EV_REL, ecodes.REL_Y, dy)
            mouse.syn()
        prev_centroid = (cx, cy)
        prev_t = t

    print(f'Three-finger drag daemon started '
          f'({"proxy (Wayland)" if proxy_mode else "passive (Xorg)"} mode)')

    while True:
        need_tick = ((dragging and release_time is not None)
                     or pending or resync_at is not None)
        r, _, _ = select.select([touchpad.fd], [], [],
                                0.03 if need_tick else None)

        if r:
            try:
                events = list(touchpad.read())
            except OSError:
                break

            for event in events:
                if event.type == ecodes.EV_SYN:
                    if event.code == ecodes.SYN_DROPPED:
                        # kernel queue overflow: our per-slot state is no
                        # longer trustworthy. Reset; it self-heals as
                        # contacts end and new ones arrive.
                        slots.clear()
                        finish_drag()
                        continue
                    if event.code != ecodes.SYN_REPORT:
                        continue
                else:
                    if event.type == ecodes.EV_ABS:
                        if event.code == ecodes.ABS_MT_SLOT:
                            current_slot = event.value
                        elif event.code == ecodes.ABS_MT_TRACKING_ID:
                            if event.value == -1:
                                slots.pop(current_slot, None)
                            else:
                                slots[current_slot] = {}
                        elif (event.code >= ecodes.ABS_MT_TOUCH_MAJOR
                              and current_slot in slots):
                            slots[current_slot][event.code] = event.value
                    elif (event.type == ecodes.EV_KEY
                          and event.code in BUTTON_CODES):
                        btn_state[event.code] = event.value
                    if proxy_mode:
                        # keep original timestamps: libinput uses them for
                        # velocity, so re-stamping adds jitter felt as lag
                        frame_buf += EVENT_STRUCT.pack(
                            event.sec, event.usec,
                            event.type, event.code, event.value)
                    continue

                # --- end of one hardware frame (SYN_REPORT) ---
                n = len(slots)
                t = event.sec + event.usec / 1e6

                if dragging:
                    # the whole drag stays hidden from the compositor;
                    # any number of remaining fingers steers it
                    if proxy_mode:
                        suppressed = True
                        resync_at = None
                    if n == 0:
                        if release_time is None:
                            release_time = time.monotonic()
                    else:
                        release_time = None
                        cx = sum(v.get(ecodes.ABS_MT_POSITION_X, 0)
                                 for v in slots.values()) / n
                        cy = sum(v.get(ecodes.ABS_MT_POSITION_Y, 0)
                                 for v in slots.values()) / n
                        drag_motion(cx, cy, t, n)
                elif n == 3:
                    if proxy_mode:
                        suppressed = True
                        resync_at = None
                    cx = sum(v.get(ecodes.ABS_MT_POSITION_X, 0)
                             for v in slots.values()) / 3
                    cy = sum(v.get(ecodes.ABS_MT_POSITION_Y, 0)
                             for v in slots.values()) / 3
                    if not pending:
                        # fingers just arrived: arm, don't click yet
                        pending = True
                        pend_t = t
                        cum_dist = 0.0
                        prev_centroid = (cx, cy)
                        prev_t = t
                        v_ema = 0.0
                    else:
                        mag = ((cx - prev_centroid[0]) ** 2
                               + (cy - prev_centroid[1]) ** 2) ** 0.5
                        cum_dist += mag
                        prev_centroid = (cx, cy)
                        prev_t = t
                        if (cum_dist > DRAG_START_DISTANCE
                                or t - pend_t > DRAG_START_HOLD):
                            start_drag(3)
                elif n > 3:
                    # 4+ fingers and no drag: hide it (it is not a drag,
                    # and letting a partial gesture through confuses the
                    # compositor), and disarm
                    pending = False
                    if proxy_mode:
                        suppressed = True
                        resync_at = None
                else:
                    pending = False   # armed but never moved: no stray click
                    if suppressed:
                        if n == 0:
                            # everything lifted: safe to resync now, the
                            # clone gets nothing placed, so no ghost taps
                            suppressed = False
                            resync_at = None
                            resync_clone()
                        elif resync_at is None:
                            # fingers remain: wait RESYNC_GRACE before
                            # showing them — a staggered lift would look
                            # like a quick 2-finger tap (ghost right-click)
                            resync_at = time.monotonic() + RESYNC_GRACE
                        elif time.monotonic() >= resync_at:
                            suppressed = False
                            resync_at = None
                            resync_clone()
                    elif proxy_mode:
                        os.write(clone.fd,
                                 bytes(frame_buf) + EVENT_STRUCT.pack(
                                     event.sec, event.usec,
                                     ecodes.EV_SYN, ecodes.SYN_REPORT, 0))
                        clone_slots.clear()
                        clone_slots.update(slots.keys())
                        clone_count = n
                        clone_btn.clear()
                        clone_btn.update(btn_state)

                frame_buf.clear()

        # --- timer-driven work (fires even with no touchpad events) ---
        if pending and time.time() - pend_t > DRAG_START_HOLD:
            # deliberate stationary 3-finger hold: grab without motion
            start_drag(3)
        if (suppressed and not dragging and resync_at is not None
                and time.monotonic() >= resync_at):
            suppressed = False
            resync_at = None
            resync_clone()
        if dragging and release_time and (
                time.monotonic() - release_time > DRAG_RELEASE_DELAY):
            finish_drag()


if __name__ == '__main__':
    main()
