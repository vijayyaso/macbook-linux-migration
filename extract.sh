#!/bin/bash
# Mac Settings Extractor
# Run this on macOS. It reads Apple's trackpad, scrolling, and ambient-light
# sensor values and writes them to mac-values.txt so they can be used to tune
# an equivalent feel on Linux. Reads settings only - changes nothing.

OUT="$(cd "$(dirname "$0")" && pwd)/mac-values.txt"
exec > >(tee "$OUT") 2>&1

section() { echo; echo "===== $1 ====="; }

section "System"
sw_vers 2>/dev/null
sysctl -n hw.model 2>/dev/null

section "Trackpad tracking speed (com.apple.trackpad.scaling, range 0-3)"
defaults read -g com.apple.trackpad.scaling 2>/dev/null || echo "(not set = system default 0.6875)"

section "Mouse tracking speed (com.apple.mouse.scaling)"
defaults read -g com.apple.mouse.scaling 2>/dev/null || echo "(not set)"

section "Scroll speed (com.apple.scrollwheel.scaling)"
defaults read -g com.apple.scrollwheel.scaling 2>/dev/null || echo "(not set = default 0.75)"

section "Natural scrolling (com.apple.swipescrolldirection)"
defaults read -g com.apple.swipescrolldirection 2>/dev/null || echo "(not set = default 1/on)"

section "Double-click threshold (com.apple.mouse.doubleClickThreshold)"
defaults read -g com.apple.mouse.doubleClickThreshold 2>/dev/null || echo "(not set = default 0.5)"

section "Built-in trackpad preferences (com.apple.AppleMultitouchTrackpad)"
defaults read com.apple.AppleMultitouchTrackpad 2>/dev/null || echo "(none)"

section "Bluetooth trackpad preferences"
defaults read com.apple.driver.AppleBluetoothMultitouch.trackpad 2>/dev/null || echo "(none)"

section "Ambient light sensor - 10 samples over 20s"
echo "Cover / uncover the camera area while this runs to capture the range."
for i in $(seq 1 10); do
  lux=$(ioreg -r -c AppleLMUController 2>/dev/null | grep -i lux)
  [ -z "$lux" ] && lux=$(ioreg -r -c AppleHIDALSService 2>/dev/null | grep -iE '"(CurrentLux|ALSSensorData|Lux)"')
  [ -z "$lux" ] && lux="(no ALS reading found via ioreg)"
  echo "sample $i: $lux"
  sleep 2
done

section "Current display brightness"
ioreg -c AppleBacklightDisplay 2>/dev/null | grep -i '"brightness"' | head -2 || echo "(not found)"

echo
echo "Done. Values saved to: $OUT"
echo "Either 'git add mac-values.txt && git commit -m \"add extracted values\" && git push'"
echo "or copy-paste the contents back to Claude on the Linux side."
