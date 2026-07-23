# Mac Settings Extractor

Reads macOS trackpad, scrolling, and ambient-light-sensor values on a MacBook
so they can be used to tune the same feel on a Linux install of the same
machine (built for a MacBookPro11,4 dual-booting Zorin OS). **Read-only** —
it changes no settings.

## How to use (on macOS)

```sh
git clone https://github.com/vijayyaso/mac-settings-extractor.git
cd mac-settings-extractor
bash extract.sh
```

While the ambient-light section runs (20 seconds), wave your hand over the
camera area so the samples capture both dark and bright readings.

The results land in `mac-values.txt`. Send them back to the Linux side either
way:

```sh
git add mac-values.txt
git commit -m "add extracted values"
git push
```

…or just copy-paste the file contents into Claude Code on Linux.

## What gets extracted

| Value | Used for on Linux |
|---|---|
| `com.apple.trackpad.scaling` | GNOME touchpad pointer speed |
| `com.apple.scrollwheel.scaling` | Scroll speed feel |
| `com.apple.swipescrolldirection` | Natural scrolling on/off |
| `AppleMultitouchTrackpad` prefs | Tap-to-click, three-finger drag, click firmness |
| ALS lux samples | Calibrating webcam-based auto-brightness mapping |
| Display brightness | Cross-checking brightness scale |
