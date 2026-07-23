# three-finger-drag

macOS-style **three-finger drag** for Linux touchpads — works on **both
Wayland and Xorg**, including GNOME Wayland where the compositor's own
3-finger workspace swipe normally makes this impossible.

Move windows, select text, and drag files by placing three fingers on the
touchpad and moving them — exactly like enabling *Three Finger Drag* on a
MacBook. Four-finger swipes still reach the desktop, so compositor
gestures (workspace switch, overview) keep working — the full macOS
layout: **3 fingers = drag, 4 fingers = swipe**.

## Why this exists

Native three-finger drag landed in libinput 1.28, but distributions on
older LTS bases (e.g. Ubuntu 24.04 / Zorin 18 with libinput 1.25) will
never receive it, and no GNOME release exposes it yet. GNOME extensions
can only remap swipe gestures — they cannot inject a held mouse button.
This daemon fills the gap at the kernel-input level, beneath the display
server, so it works the same on Wayland and Xorg.

## How it works

- **Passive mode (Xorg):** the daemon just watches the touchpad and, during
  a drag, holds button 1 on a `uinput` virtual mouse and steers it with the
  finger centroid. Zero added latency for normal cursor use.
- **Proxy mode (Wayland, auto-detected):** GNOME's 3-finger workspace swipe
  cannot be disabled, so the daemon exclusively grabs the touchpad
  (`EVIOCGRAB`) and mirrors every event to a `uinput` clone that the
  compositor reads instead. While a gesture is in progress the mirror is
  paused — the desktop never sees the 3 fingers — and the drag is injected
  through the virtual mouse.

Details that make it feel right:

- **macOS-style analog acceleration** — pointer gain scales continuously
  with finger velocity: slow = pixel precision, fast = full-screen throws.
- **Finger-identity tracking** — the drag is steered only by the three
  fingers that started it. Extra contacts (a palm heel or thumb brushing
  the pad edge mid-drag) are ignored entirely. Lifting a tracked finger
  freezes the drag in place; re-placing three fingers within the
  drag-lock window resumes it, otherwise it ends.
- **Palm-size rejection** (recognized Apple trackpads) — a palm heel
  resting alongside two real fingers won't be miscounted as the third and
  arm a drag; the size thresholds match libinput's own hwdb quirks for
  the same hardware.
- **Dead zone + hold-to-grab** — a still 3-finger tap never fires a stray
  click; moving ~0.8 mm or holding ¼ s engages the drag.
- **Hardware identity passthrough** — the clone inherits the real
  vendor/product IDs so libinput applies the correct hardware quirks
  (e.g. Apple touchpads' light-touch filtering).
- **Timestamp passthrough** — mirrored events keep original kernel
  timestamps, so libinput's velocity model (and pointer feel) is unchanged.
- **Teleport guard & re-anchoring** — finger clipping at pad edges or
  finger-count changes re-anchor instead of jerking the pointer.
- **Ghost-tap prevention** — staggered finger lifts are held back briefly
  so they can't register as phantom 2-finger taps (right-clicks).
- **4-finger swipe translation** (proxy mode) — since 3 fingers are
  reserved for the drag, a 4-finger swipe is replayed to the compositor
  as a 3-finger swipe (three of the real fingers are forwarded live), so
  GNOME's native gestures fire: 4-finger left/right switches workspace,
  4-finger up opens the overview. A still 4-finger tap shows the desktop
  nothing.

## Requirements

- Linux with `uinput` (any modern kernel)
- Python 3.8+ and `python3-evdev`
- Your user in the `input` group, and `input`-group access to `/dev/uinput`
  (the installer sets both up)
- systemd user session

## Install

```bash
./install.sh
```

Log out and back in if the script just added you to the `input` group.

## Tuning

All feel parameters are named constants at the top of
`three-finger-drag.py` — gain curve (`BASE_GAIN`, `GAIN_REF_SPEED`,
`MAX_GAIN`), dead zone (`DRAG_START_DISTANCE`), hold-to-grab
(`DRAG_START_HOLD`) and drag-lock (`DRAG_RELEASE_DELAY`) timings.
After editing:

```bash
systemctl --user restart three-finger-drag
```

## Troubleshooting

- **Touchpad misbehaves?** `systemctl --user stop three-finger-drag`
  instantly restores stock behavior (the kernel releases the grab).
- **Logs:** `journalctl --user -u three-finger-drag -f`
- The daemon exits gracefully and un-grabs the touchpad on crash; systemd
  restarts it.

## Status / roadmap

When your distribution ships libinput ≥ 1.28 with a compositor that
exposes native three-finger drag, prefer the native implementation and
retire this daemon.

## License

MIT — see [LICENSE](LICENSE).
