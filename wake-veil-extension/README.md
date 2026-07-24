# Wake Veil (GNOME extension)

macOS-style **fade-from-black on wake from suspend**: a black veil is placed
over the screen just before sleeping, so the first frame after resume is clean
black which then fades out smoothly once the session has settled — instead of
an abrupt desktop pop-in.

Includes a failsafe timer so a stuck veil is impossible.

> **Why not a blur?** The first version used a live `Shell.BlurEffect` over the
> whole stage. On a 2015 Iris Pro at 2880×1800 that costs *seconds per frame*
> and delayed the visible wake by 5–6s (A/B measured). A plain fade costs
> nothing. If you have a modern GPU, re-adding the blur is a 5-line change.

## Install

```bash
cp -r wake-veil@vijayyaso ~/.local/share/gnome-shell/extensions/
# log out and back in (GNOME only scans extensions at session start), then:
gnome-extensions enable wake-veil@vijayyaso
```

Tested on GNOME Shell 46 (Wayland). For other versions adjust
`shell-version` in `metadata.json`.

## Tune

Constants at the top of `extension.js`: `SETTLE_MS` (hold before fading,
default 900ms), `FADE_MS` (fade duration, 600ms), `FAILSAFE_MS` (hard ceiling).
