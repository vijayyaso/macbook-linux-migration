# lid-instant-wake

Mac-like lid behavior for laptops whose firmware makes real sleep slow to wake
(built for the MacBookPro11,4, where deep-sleep lid wake has an unfixable ~3s
firmware floor — see [`../docs/suspend-resume-fix.md`](../docs/suspend-resume-fix.md)).

**Behavior:**
- Lid closed → display off + keyboard backlight off instantly; machine stays awake.
- Lid reopened → everything back in under a second. Feels like a Mac.
- Lid closed longer than the battery-aware delay (**60 min on AC, 15 min on
  battery**, macOS `standbydelay`-style) → real suspend (deep S3).
- The watcher re-enables the display right before suspending — entering S3 with
  DPMS off delays panel light-up on resume.

**Trade-off:** during the fake-sleep window the machine idles instead of
sleeping (~1–2% battery per 15 min). Don't stuff it in a padded bag for long
with the lid just closed — same caveat as a MacBook doing Power Nap.

## Install

```bash
# 1. Watcher script + user service
install -Dm755 lid-instant-wake ~/.local/bin/lid-instant-wake
install -Dm644 lid-instant-wake.service ~/.config/systemd/user/lid-instant-wake.service
systemctl --user daemon-reload
systemctl --user enable --now lid-instant-wake.service

# 2. Stop logind from suspending on lid close
sudo install -Dm644 lid-instant-wake.conf /etc/systemd/logind.conf.d/lid-instant-wake.conf
sudo systemctl restart systemd-logind

# 3. Stop GNOME from suspending on lid close
gsettings set org.gnome.settings-daemon.plugins.power lid-close-battery-action nothing
gsettings set org.gnome.settings-daemon.plugins.power lid-close-ac-action nothing

# 4. Let the user service trigger suspend (EDIT THE USERNAME FIRST)
sudo install -Dm644 85-lid-instant-wake.rules /etc/polkit-1/rules.d/85-lid-instant-wake.rules
```

> The polkit rule contains a hard-coded username — change it to yours. It's
> needed because user services live outside the login session scope, so
> polkit's usual "active session" allowance doesn't apply to them.

## Tune

Edit the constants at the top of the script: `DELAY_AC_MIN`, `DELAY_BAT_MIN`.
Paths for the lid state, keyboard backlight LED, and AC supply are also there
if your hardware differs.

## Uninstall

```bash
systemctl --user disable --now lid-instant-wake.service
sudo rm /etc/systemd/logind.conf.d/lid-instant-wake.conf /etc/polkit-1/rules.d/85-lid-instant-wake.rules
sudo systemctl restart systemd-logind
gsettings set org.gnome.settings-daemon.plugins.power lid-close-battery-action suspend
gsettings set org.gnome.settings-daemon.plugins.power lid-close-ac-action suspend
```
