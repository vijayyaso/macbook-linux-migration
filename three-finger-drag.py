#!/usr/bin/env python3
"""Three-finger drag daemon for Xorg and Wayland — macOS-style.

Passive mode (Xorg): the daemon just watches the touchpad and injects
the drag through a virtual mouse. Zero added latency for normal use.

Proxy mode (Wayland, auto-detected): GNOME's built-in 3-finger workspace
swipe cannot be disabled, so the daemon exclusively grabs the touchpad
and mirrors its events to a uinput clone the compositor reads instead.
The mirror pauses while a gesture is in progress, hiding it from the
desktop, and the drag is injected as in passive mode.

Drag model (matches macOS):
  - 3 fingers down + movement (or a deliberate stationary hold) starts
    the drag; a still 3-finger tap does nothing.
  - The drag is steered ONLY by the three fingers that started it,
    identified by their hardware slots. Extra contacts that appear later
    (a palm heel or thumb brushing the pad edge) are ignored entirely.
  - Lifting any of the three freezes the drag in place — the held item
    stops moving but stays grabbed. Returning three fingers within the
    drag-lock window resumes; otherwise the drag ends.

4-finger gestures (proxy mode): since 3 fingers are reserved for the
drag, a 4-finger swipe is replayed to the compositor as a 3-finger
swipe (three of the real fingers are forwarded), so the desktop's
native gestures still work — on GNOME: 4-finger left/right switches
workspace, 4-finger up opens the overview. Same layout as macOS.
"""

import fcntl
import glob
import os
import select
import signal
import struct
import sys
import time
from collections import deque

import evdev
from evdev import UInput, ecodes

# --- tuning ---------------------------------------------------------------
# macOS-style analog acceleration: pointer gain scales smoothly with
# finger velocity instead of a hard two-step switch.
#   gain = BASE_GAIN * (1 + (v / GAIN_REF_SPEED) ** GAIN_EXPONENT)
# v is finger speed in touchpad units/s (bcm5974: ~97 units per mm).
BASE_GAIN = 0.13          # gain at near-zero speed: slow finger = precision
GAIN_REF_SPEED = 3500.0   # units/s where gain has roughly doubled
GAIN_EXPONENT = 1.1       # curve steepness
MAX_GAIN = 0.55           # cap so flicks stay controllable
VELOCITY_SMOOTHING = 0.5  # EMA factor for velocity (jitter suppression)

DRAG_START_DISTANCE = 20  # units (~0.2 mm) of motion before button press —
                          # a still 3-finger tap never fires a stray click
DRAG_START_HOLD = 0.25    # s of deliberate stationary hold also grabs
DRAG_RELEASE_DELAY = 0.25 # s frozen (fingers lifted) before the drag ends
RESYNC_GRACE = 0.08       # s to wait before re-showing leftover fingers to
                          # the compositor — a staggered 3-finger lift would
                          # otherwise read as a quick 2-finger tap (ghost
                          # right-click)
JUMP_GUARD = 400          # units (~4 mm/frame): any single tracked finger
                          # jumping farther than this in one frame is a
                          # sensor glitch (edge clipping) — re-anchor
                          # instead of jerking the pointer
LIFTOFF_GUARD_FRAMES = 2  # motion is emitted this many frames late; when a
                          # finger lifts, the buffered tail is discarded so
                          # the fingertip peel-off at drag end doesn't scoot
                          # the item a little further (~16 ms extra drag
                          # latency, imperceptible)
FOUR_START_DISTANCE = 100 # units (~1 mm) the 4-finger centroid must move
                          # before the gesture is shown to the desktop as a
                          # 3-finger swipe — a still 4-finger tap shows the
                          # compositor nothing (no ghost taps)
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

ABS_X = ecodes.ABS_MT_POSITION_X
ABS_Y = ecodes.ABS_MT_POSITION_Y


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
        if ABS_X in abs_codes and ABS_Y in abs_codes:
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
    drag_slots = frozenset()   # the 3 slots steering the current drag
    prev_pos = None       # {slot: (x, y)} of drag_slots at last frame
    pending = False       # 3 fingers down, button not yet pressed
    pend_t = 0.0
    cum_dist = 0.0
    prev_centroid = None  # pending-phase movement anchor
    prev_t = 0.0
    v_ema = 0.0
    release_time = None
    res_x = res_y = 0.0
    pending_motion = deque()   # liftoff guard: delayed motion frames
    next_tid = 1
    four_latch = False    # 4-finger gesture in progress (or winding down)
    four_tracked = frozenset()  # the 3 real slots forwarded as the swipe
    four_prev = None      # previous 4-finger centroid
    four_cum = 0.0        # centroid distance travelled while 4 are down

    def slot_points(slot_set):
        return {s: (slots[s].get(ABS_X, 0), slots[s].get(ABS_Y, 0))
                for s in slot_set}

    def start_drag(t):
        nonlocal pending, dragging, drag_slots, prev_pos, prev_t
        nonlocal res_x, res_y, v_ema
        pending = False
        dragging = True
        drag_slots = frozenset(slots.keys())
        prev_pos = slot_points(drag_slots)
        prev_t = t
        res_x = res_y = 0.0
        v_ema = 0.0
        mouse.write(ecodes.EV_KEY, ecodes.BTN_LEFT, 1)
        mouse.syn()

    def end_drag():
        nonlocal dragging, pending, drag_slots, prev_pos, prev_centroid
        nonlocal release_time, v_ema, res_x, res_y
        if dragging:
            mouse.write(ecodes.EV_KEY, ecodes.BTN_LEFT, 0)
            mouse.syn()
        dragging = False
        pending = False
        drag_slots = frozenset()
        prev_pos = None
        prev_centroid = None
        v_ema = 0.0
        res_x = res_y = 0.0
        release_time = None
        pending_motion.clear()

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

    def emit_clone_frame(pairs, sec, usec):
        # one batched frame with real kernel timestamps (libinput's
        # velocity model depends on them)
        buf = b''.join(EVENT_STRUCT.pack(sec, usec, t, c, v)
                       for t, c, v in pairs)
        buf += EVENT_STRUCT.pack(sec, usec,
                                 ecodes.EV_SYN, ecodes.SYN_REPORT, 0)
        os.write(clone.fd, buf)

    def lift_clone_touches():
        # one frame lifting every finger the clone still believes is down
        nonlocal clone_count
        if not clone_slots:
            return
        for s in clone_slots:
            clone.write(ecodes.EV_ABS, ecodes.ABS_MT_SLOT, s)
            clone.write(ecodes.EV_ABS, ecodes.ABS_MT_TRACKING_ID, -1)
        if clone_count in TOOL_BITS:
            clone.write(ecodes.EV_KEY, TOOL_BITS[clone_count], 0)
        clone.write(ecodes.EV_KEY, ecodes.BTN_TOUCH, 0)
        clone.syn()
        clone_slots.clear()
        clone_count = 0

    def resync_clone():
        # After a suppression window the clone's picture is stale.
        # Frame 1 lifts everything it still holds; frame 2 places the
        # fingers that are really down right now with fresh tracking ids
        # and reconciles physical button state (a click released while
        # suppressed would otherwise leave the clone's button stuck).
        nonlocal clone_count, next_tid
        lift_clone_touches()
        wrote = False
        if slots:
            for s, axes in slots.items():
                clone.write(ecodes.EV_ABS, ecodes.ABS_MT_SLOT, s)
                clone.write(ecodes.EV_ABS, ecodes.ABS_MT_TRACKING_ID, next_tid)
                next_tid = next_tid % 65535 + 1
                for code, value in axes.items():
                    clone.write(ecodes.EV_ABS, code, value)
            first = next(iter(slots.values()))
            clone.write(ecodes.EV_ABS, ecodes.ABS_X, first.get(ABS_X, 0))
            clone.write(ecodes.EV_ABS, ecodes.ABS_Y, first.get(ABS_Y, 0))
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

    def steer_drag(t):
        # Move by the average delta of the three tracked fingers.
        # A single finger teleporting (sensor clipping at the pad edge)
        # re-anchors the frame instead of jerking the pointer.
        nonlocal prev_pos, prev_t, v_ema, res_x, res_y
        pts = slot_points(drag_slots)
        if prev_pos is None or set(prev_pos) != set(pts):
            prev_pos = pts
            prev_t = t
            return
        dt = min(max(t - prev_t, 0.002), 0.05)
        deltas = [(pts[s][0] - prev_pos[s][0], pts[s][1] - prev_pos[s][1])
                  for s in drag_slots]
        worst = max((dx * dx + dy * dy) ** 0.5 for dx, dy in deltas)
        if worst > v_ema * dt * 4 + JUMP_GUARD:
            prev_pos = pts
            prev_t = t
            return
        raw_dx = sum(d[0] for d in deltas) / 3
        raw_dy = sum(d[1] for d in deltas) / 3
        mag = (raw_dx ** 2 + raw_dy ** 2) ** 0.5
        v = mag / dt
        v_ema = VELOCITY_SMOOTHING * v + (1 - VELOCITY_SMOOTHING) * v_ema
        gain = min(MAX_GAIN, BASE_GAIN * (
            1 + (v_ema / GAIN_REF_SPEED) ** GAIN_EXPONENT))
        fx = raw_dx * gain + res_x
        fy = raw_dy * gain + res_y
        dx, dy = int(fx), int(fy)
        res_x, res_y = fx - dx, fy - dy
        # liftoff guard: emit through a short delay buffer so the last
        # frames before a finger lifts (fingertip peel-off) can be
        # discarded instead of scooting the item at drag end
        pending_motion.append((dx, dy))
        while len(pending_motion) > LIFTOFF_GUARD_FRAMES:
            odx, ody = pending_motion.popleft()
            if odx or ody:
                mouse.write(ecodes.EV_REL, ecodes.REL_X, odx)
                mouse.write(ecodes.EV_REL, ecodes.REL_Y, ody)
                mouse.syn()
        prev_pos = pts
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
                        four_latch = False
                        four_tracked = frozenset()
                        four_prev = None
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
                    # the whole drag stays hidden from the compositor
                    if proxy_mode:
                        suppressed = True
                        resync_at = None
                    if drag_slots <= slots.keys():
                        # all three tracked fingers present: steer.
                        # Extra contacts (palm heel / thumb at the pad
                        # edge) are ignored completely.
                        release_time = None
                        steer_drag(t)
                    elif n == 3:
                        # a fresh threesome (fingers re-placed during
                        # drag lock): adopt it and continue the drag
                        drag_slots = frozenset(slots.keys())
                        prev_pos = slot_points(drag_slots)
                        prev_t = t
                        release_time = None
                        pending_motion.clear()
                    else:
                        # tracked finger(s) lifted: freeze in place —
                        # the item stays grabbed but does NOT move, and
                        # the buffered peel-off motion is discarded
                        pending_motion.clear()
                        if release_time is None:
                            release_time = time.monotonic()
                elif n >= 4 or four_latch:
                    # 4-finger gesture: since 3 fingers are reserved for
                    # the drag, replay this to the compositor as a
                    # 3-finger swipe by forwarding three of the real
                    # fingers — GNOME's native workspace-switch /
                    # overview gestures fire (macOS layout: 3 = drag,
                    # 4 = swipe). Passive mode (Xorg) needs nothing:
                    # the desktop sees the real events anyway.
                    pending = False
                    if proxy_mode:
                        suppressed = True
                        resync_at = None
                        if n >= 4:
                            four_latch = True
                            cx = sum(v.get(ABS_X, 0)
                                     for v in slots.values()) / n
                            cy = sum(v.get(ABS_Y, 0)
                                     for v in slots.values()) / n
                            if four_prev is None:
                                four_cum = 0.0
                            else:
                                four_cum += (
                                    (cx - four_prev[0]) ** 2
                                    + (cy - four_prev[1]) ** 2) ** 0.5
                            four_prev = (cx, cy)
                            if four_tracked:
                                if four_tracked <= slots.keys():
                                    # steer: forward the tracked fingers'
                                    # real positions (and touch size, so
                                    # hardware quirks keep applying)
                                    pairs = []
                                    for s in sorted(four_tracked):
                                        pairs.append(
                                            (ecodes.EV_ABS,
                                             ecodes.ABS_MT_SLOT, s))
                                        pairs.extend(
                                            (ecodes.EV_ABS, code, value)
                                            for code, value
                                            in slots[s].items())
                                    first = slots[min(four_tracked)]
                                    pairs.append(
                                        (ecodes.EV_ABS, ecodes.ABS_X,
                                         first.get(ABS_X, 0)))
                                    pairs.append(
                                        (ecodes.EV_ABS, ecodes.ABS_Y,
                                         first.get(ABS_Y, 0)))
                                    emit_clone_frame(
                                        pairs, event.sec, event.usec)
                                else:
                                    # a tracked finger vanished
                                    # mid-gesture: end the swipe cleanly;
                                    # renewed motion starts a fresh one
                                    lift_clone_touches()
                                    four_tracked = frozenset()
                                    four_prev = None
                            elif four_cum > FOUR_START_DISTANCE:
                                # moving with intent: show three of the
                                # four fingers as a 3-finger swipe.
                                # Fingers the clone already holds (from
                                # mirroring before suppression) are kept
                                # alive, not re-placed — no lift means no
                                # ghost tap at swipe start.
                                keep = sorted(set(clone_slots)
                                              & slots.keys())
                                extra = [s for s in sorted(slots)
                                         if s not in clone_slots]
                                tracked = (keep + extra)[:3]
                                pairs = []
                                for s in sorted(set(clone_slots)
                                                - set(tracked)):
                                    pairs.append(
                                        (ecodes.EV_ABS,
                                         ecodes.ABS_MT_SLOT, s))
                                    pairs.append(
                                        (ecodes.EV_ABS,
                                         ecodes.ABS_MT_TRACKING_ID, -1))
                                for s in tracked:
                                    pairs.append(
                                        (ecodes.EV_ABS,
                                         ecodes.ABS_MT_SLOT, s))
                                    if s not in clone_slots:
                                        pairs.append(
                                            (ecodes.EV_ABS,
                                             ecodes.ABS_MT_TRACKING_ID,
                                             next_tid))
                                        next_tid = next_tid % 65535 + 1
                                    pairs.extend(
                                        (ecodes.EV_ABS, code, value)
                                        for code, value
                                        in slots[s].items())
                                first = slots[tracked[0]]
                                pairs.append(
                                    (ecodes.EV_ABS, ecodes.ABS_X,
                                     first.get(ABS_X, 0)))
                                pairs.append(
                                    (ecodes.EV_ABS, ecodes.ABS_Y,
                                     first.get(ABS_Y, 0)))
                                if (clone_count != 3
                                        and clone_count in TOOL_BITS):
                                    pairs.append(
                                        (ecodes.EV_KEY,
                                         TOOL_BITS[clone_count], 0))
                                if clone_count != 3:
                                    pairs.append(
                                        (ecodes.EV_KEY,
                                         ecodes.BTN_TOOL_TRIPLETAP, 1))
                                if not clone_slots:
                                    pairs.append(
                                        (ecodes.EV_KEY,
                                         ecodes.BTN_TOUCH, 1))
                                emit_clone_frame(
                                    pairs, event.sec, event.usec)
                                four_tracked = frozenset(tracked)
                                clone_slots.clear()
                                clone_slots.update(tracked)
                                clone_count = 3
                        else:
                            # fingers lifting: complete the synthetic
                            # swipe now, and stay suppressed until ALL
                            # fingers are up so the staggered liftoff can
                            # neither arm a drag nor ghost-tap
                            if four_tracked:
                                lift_clone_touches()
                                four_tracked = frozenset()
                            four_prev = None
                            if n == 0:
                                four_latch = False
                                suppressed = False
                                resync_clone()
                elif n == 3:
                    if proxy_mode:
                        suppressed = True
                        resync_at = None
                    cx = sum(v.get(ABS_X, 0) for v in slots.values()) / 3
                    cy = sum(v.get(ABS_Y, 0) for v in slots.values()) / 3
                    if not pending:
                        # fingers just arrived: arm, don't click yet
                        pending = True
                        pend_t = t
                        cum_dist = 0.0
                        prev_centroid = (cx, cy)
                    else:
                        cum_dist += ((cx - prev_centroid[0]) ** 2
                                     + (cy - prev_centroid[1]) ** 2) ** 0.5
                        prev_centroid = (cx, cy)
                        if (cum_dist > DRAG_START_DISTANCE
                                or t - pend_t > DRAG_START_HOLD):
                            start_drag(t)
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
            start_drag(time.time())
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
