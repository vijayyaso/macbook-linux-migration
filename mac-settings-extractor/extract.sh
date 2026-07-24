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

section "Keyboard feel (repeat rate / initial delay / press-and-hold)"
echo "KeyRepeat:          $(defaults read -g KeyRepeat 2>/dev/null || echo 'default 6 (~90ms)')"
echo "InitialKeyRepeat:   $(defaults read -g InitialKeyRepeat 2>/dev/null || echo 'default 25 (~375ms)')"
echo "ApplePressAndHold:  $(defaults read -g ApplePressAndHoldEnabled 2>/dev/null || echo 'default 1')"

section "Function keys behave as F1-F12 (com.apple.keyboard.fnState)"
defaults read -g com.apple.keyboard.fnState 2>/dev/null || echo "(not set = media keys first)"

section "Keyboard backlight settings"
defaults read com.apple.BezelServices 2>/dev/null | grep -iE "dim|auto" || echo "(none)"
ioreg -c AppleHIDKeyboardEventDriverV2 2>/dev/null | grep -i backlight | head -3

# Print one preference key with its label and the default used when unset.
gkey() { printf '%-48s %s\n' "$1:" "$(defaults read -g "$1" 2>/dev/null || echo "(not set = $2)")"; }
dkey() { printf '%-48s %s\n' "$2:" "$(defaults read "$1" "$2" 2>/dev/null || echo "(not set = $3)")"; }

section "Dock behaviour (com.apple.dock)"
dkey com.apple.dock tilesize "default ~64"
dkey com.apple.dock magnification "default 0/off"
dkey com.apple.dock largesize "default ~128"
dkey com.apple.dock autohide "default 0/off"
dkey com.apple.dock autohide-delay "default 0.5s"
dkey com.apple.dock autohide-time-modifier "default ~0.5s animation"
dkey com.apple.dock mineffect "default genie"
dkey com.apple.dock minimize-to-application "default 0/own thumbnail"
dkey com.apple.dock launchanim "default 1/bounce on launch"
dkey com.apple.dock orientation "default bottom"
dkey com.apple.dock show-recents "default 1/on"

section "Hot corners (com.apple.dock wvous-*; 1=off 2=MissionControl 3=AppWindows 4=Desktop 5=ScreenSaver 6=DisableSaver 10=DisplaySleep 11=Launchpad 12=NotificationCenter 13=LockScreen 14=QuickNote)"
for c in tl tr bl br; do
  dkey com.apple.dock "wvous-$c-corner" "default: br=QuickNote, others off"
  dkey com.apple.dock "wvous-$c-modifier" "default 0/no modifier"
done

section "Mission Control / Spaces behaviour"
dkey com.apple.dock mru-spaces "default 1/auto-rearrange Spaces by use"
dkey com.apple.dock expose-group-apps "default 0/windows not grouped by app"
dkey com.apple.dock expose-animation-duration "default ~0.2s"
gkey AppleSpacesSwitchOnActivate "default 1/switch to app's Space"
dkey com.apple.spaces spans-displays "default 0/displays have separate Spaces"

section "Window behaviour & UI feel (NSGlobalDomain)"
gkey AppleActionOnDoubleClick "default Maximize/zoom on title-bar double-click"
gkey AppleShowScrollBars "default Automatic"
gkey AppleScrollerPagingBehavior "default 0/click scroll bar jumps one page"
gkey NSAutomaticWindowAnimationsEnabled "default 1/window open-close animations on"
gkey NSWindowResizeTime "default 0.2s"
gkey CGDisableCursorLocationMagnification "default 0/shake-to-locate cursor on"
gkey _HIHideMenuBar "default 0/menu bar always visible"
gkey AppleInterfaceStyle "not set = Light mode"
gkey AppleInterfaceStyleSwitchesAutomatically "default 0/no auto light-dark"
gkey AppleAccentColor "multicolour accent"
gkey AppleHighlightColor "accent-matched highlight"
gkey NSTableViewDefaultSizeMode "default 2/medium sidebar icons"

section "Accessibility motion/transparency (com.apple.universalaccess)"
dkey com.apple.universalaccess reduceMotion "default 0/full animations"
dkey com.apple.universalaccess reduceTransparency "default 0/translucent UI"

section "Text input behaviours (NSGlobalDomain)"
gkey NSAutomaticSpellingCorrectionEnabled "default 1/autocorrect on"
gkey NSAutomaticCapitalizationEnabled "default 1/auto-capitalize on"
gkey NSAutomaticQuoteSubstitutionEnabled "default 1/smart quotes on"
gkey NSAutomaticDashSubstitutionEnabled "default 1/smart dashes on"
gkey NSAutomaticPeriodSubstitutionEnabled "default 1/double-space period on"
gkey AppleKeyboardUIMode "default 0/full keyboard access off"

section "Navigation gestures (NSGlobalDomain)"
gkey AppleEnableSwipeNavigateWithScrolls "default 1/two-finger swipe between pages"
gkey AppleEnableMouseSwipeNavigateWithScrolls "default 0"

section "Modifier key remaps"
defaults -currentHost read -g 2>/dev/null | grep -A20 -i modifiermapping || echo "(no per-host modifier remaps)"
hidutil property --get "UserKeyMapping" 2>/dev/null | grep -v '^(null)$'

section "Locale, language, and formats"
gkey AppleLanguages "system default"
gkey AppleLocale "system default"
gkey AppleMeasurementUnits "per locale"
gkey AppleMetricUnits "per locale"
gkey AppleTemperatureUnit "per locale"
gkey AppleICUForce24HourTime "per locale 12/24h"
gkey AppleFirstWeekday "per locale"
printf '%-48s %s\n' "Time zone:" "$(readlink /etc/localtime 2>/dev/null | sed 's|.*zoneinfo/||' || echo '(unknown)')"

section "Keyboard layouts / input sources (com.apple.HIToolbox)"
dkey com.apple.HIToolbox AppleEnabledInputSources "system default layout"
dkey com.apple.HIToolbox AppleSelectedInputSources "system default layout"
dkey com.apple.HIToolbox AppleFnUsageType "default/no globe-key action"

section "Screenshots (com.apple.screencapture)"
dkey com.apple.screencapture location "default ~/Desktop"
dkey com.apple.screencapture type "default png"
dkey com.apple.screencapture disable-shadow "default 0/shadow on"
dkey com.apple.screencapture include-date "default 1/date in filename"
dkey com.apple.screencapture show-thumbnail "default 1/floating thumbnail"

section "Finder behaviour (curated)"
gkey AppleShowAllExtensions "default 0/hide extensions"
dkey com.apple.finder AppleShowAllFiles "default 0/hide hidden files"
dkey com.apple.finder ShowPathbar "default 0/off"
dkey com.apple.finder ShowStatusBar "default 0/off"
dkey com.apple.finder ShowHardDrivesOnDesktop "default 0/off"
dkey com.apple.finder ShowExternalHardDrivesOnDesktop "default 1/on"
dkey com.apple.finder ShowRemovableMediaOnDesktop "default 1/on"
dkey com.apple.finder ShowMountedServersOnDesktop "default 0/off"
dkey com.apple.finder NewWindowTarget "default Recents"
dkey com.apple.finder FXPreferredViewStyle "default icnv/icon view"
dkey com.apple.finder FXDefaultSearchScope "default SCev/search this Mac"
dkey com.apple.finder FXEnableExtensionChangeWarning "default 1/warn"
dkey com.apple.finder _FXSortFoldersFirst "default 0/mixed"
dkey com.apple.finder WarnOnEmptyTrash "default 1/warn"

section "Sound behaviour"
gkey com.apple.sound.beep.sound "default Boop/system alert"
gkey com.apple.sound.beep.volume "default 1.0"
gkey com.apple.sound.beep.feedback "default 0/no beep on volume keys"
gkey com.apple.sound.beep.flash "default 0/no screen flash"
dkey com.apple.systemsound com.apple.sound.uiaudio.enabled "default 1/UI sound effects on"
printf '%-48s %s\n' "Current volume state:" "$(osascript -e 'get volume settings' 2>/dev/null || echo '(unavailable)')"

section "Screen lock & screensaver"
printf '%-48s %s\n' "screensaver idleTime (per-host):" "$(defaults -currentHost read com.apple.screensaver idleTime 2>/dev/null || echo '(not set = default 1200s/20min)')"
dkey com.apple.screensaver askForPassword "default 1/require password"
dkey com.apple.screensaver askForPasswordDelay "default 0s"

section "Night Shift / blue light (com.apple.CoreBrightness)"
ns=$(defaults read com.apple.CoreBrightness 2>/dev/null | grep -iA12 "bluelight" | head -30)
[ -n "$ns" ] && echo "$ns" || echo "(needs sudo: sudo defaults read /private/var/root/Library/Preferences/com.apple.CoreBrightness.plist | grep -iA14 BlueLight)"

section "Font rendering"
gkey AppleFontSmoothing "default/medium smoothing"
gkey CGFontRenderingFontSmoothingDisabled "default/smoothing enabled"

section "Cursor & accessibility extras"
dkey com.apple.universalaccess mouseDriverCursorSize "default 1.0/normal cursor"
dkey com.apple.universalaccess closeViewScrollWheelToggle "default 0/scroll-zoom off"

section "Menu bar clock (com.apple.menuextra.clock)"
defaults read com.apple.menuextra.clock 2>/dev/null || echo "(defaults: day-of-week + time, no seconds)"

section "Menu bar / Control Centre battery percentage"
dkey com.apple.controlcenter BatteryShowPercentage "default 0/off"

section "Dock pinned apps (persistent-apps)"
defaults read com.apple.dock persistent-apps 2>/dev/null | grep '"file-label"' || echo "(default Dock apps)"

section "Default app handlers (LaunchServices - maps file types/URLs to apps)"
defaults read com.apple.LaunchServices/com.apple.launchservices.secure LSHandlers 2>/dev/null || echo "(all system defaults)"

section "Computer name"
scutil --get ComputerName 2>/dev/null; scutil --get LocalHostName 2>/dev/null

section "Terminal.app default profile"
dkey com.apple.Terminal "Default Window Settings" "default Basic"

section "Installed applications (/Applications) - for choosing Linux equivalents"
ls /Applications 2>/dev/null
ls "$HOME/Applications" 2>/dev/null

section "Homebrew packages (if installed)"
if command -v brew >/dev/null 2>&1; then
  echo "--- formulae ---"; brew list --formula --versions 2>/dev/null
  echo "--- casks ---"; brew list --cask --versions 2>/dev/null
else
  echo "(Homebrew not installed)"
fi

section "Raw preference domain dumps (appendix - full behaviour safety net)"
for domain in com.apple.dock com.apple.finder com.apple.universalaccess com.apple.symbolichotkeys com.apple.controlcenter; do
  echo; echo "--- defaults read $domain ---"
  defaults read "$domain" 2>/dev/null || echo "(unreadable)"
done
echo; echo "--- defaults read -g (NSGlobalDomain) ---"
defaults read -g 2>/dev/null || echo "(unreadable)"
echo; echo "--- defaults -currentHost read -g ---"
defaults -currentHost read -g 2>/dev/null || echo "(unreadable)"

section "Thermal state and CPU speed limit (pmset -g therm)"
pmset -g therm 2>/dev/null || echo "(not available)"

section "Power management settings (pmset -g custom)"
pmset -g custom 2>/dev/null || pmset -g 2>/dev/null

section "Display and GPU info"
system_profiler SPDisplaysDataType 2>/dev/null | grep -viE "serial|uuid"

section "Battery health (cycle count / condition)"
system_profiler SPPowerDataType 2>/dev/null | grep -viE "serial|uuid|address" | grep -iE "cycle|condition|capacity|charge|wattage|voltage" | head -12

section "Fan speeds and CPU temperature under macOS (needs admin password)"
echo "This last section asks for your macOS password (sudo). Ctrl-C here is fine - everything above is already saved."
sudo powermetrics --samplers smc -i1000 -n1 2>/dev/null | grep -iE "fan|die temp|cpu power" || echo "(skipped or not supported)"

section "Login / background items (sudo sfltool dumpbtm)"
sudo sfltool dumpbtm 2>/dev/null | grep -E "^\s*Name:" | grep -v "(null)" | sort -u || echo "(skipped)"

section "FileVault disk encryption status (sudo fdesetup)"
sudo fdesetup status 2>/dev/null || echo "(skipped)"

section "NVRAM boot-args"
sudo nvram boot-args 2>/dev/null || echo "(none set or skipped)"

section "System sleep / network time (sudo systemsetup)"
for flag in getcomputersleep getdisplaysleep getharddisksleep getwakeonnetworkaccess getusingnetworktime getnetworktimeserver getremotelogin; do
  sudo systemsetup -$flag 2>/dev/null
done

section "Preferred Wi-Fi networks (SSIDs only - consider removing before pushing publicly)"
wifidev=$(networksetup -listallhardwareports 2>/dev/null | awk '/Wi-Fi|AirPort/{getline; print $2; exit}')
networksetup -listpreferredwirelessnetworks "${wifidev:-en0}" 2>/dev/null | head -15 || echo "(unavailable)"

echo
echo "Done. Values saved to: $OUT"
echo "Either 'git add mac-values.txt && git commit -m \"add extracted values\" && git push'"
echo "or copy-paste the contents back to Claude on the Linux side."
