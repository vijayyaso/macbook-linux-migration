# kbd-backlight-restore

Restores the keyboard backlight shortly after login via UPower's D-Bus
`SetBrightness`.

**Why:** with the ambient light sensor stuck at 0 lux (see
[`../webcam-autobrightness/`](../webcam-autobrightness/)), GNOME zeroes the
keyboard backlight at every login on these MacBooks.

## Install

```bash
install -Dm644 kbd-backlight-restore.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable kbd-backlight-restore.service
```
