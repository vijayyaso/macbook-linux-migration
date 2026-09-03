# kbd-backlight

Everything needed to keep the keyboard backlight of a 2015 MacBook Pro
(`applesmc`, `smc::kbd_backlight`) working on Linux. Four separate bugs,
four small pieces.

| File | Fixes |
|---|---|
| `kbd-backlight-restore.service` (user unit) | GNOME zeroes the backlight at every login because the ambient light sensor reads 0 lux (see [`../webcam-autobrightness/`](../webcam-autobrightness/)). Sets it back via UPower 20 s after login. |
| `81-macbook-kbd-backlight.rules` (udev) | `applesmc` ships with `default_trigger = "nand-disk"`, so the backlight dims and blinks in time with SSD I/O. Forces the trigger to `none`. |
| `kbd-backlight.sleep-hook` (`/lib/systemd/system-sleep/`) | The SMC cuts backlight power on lid close/sleep and resumes at brightness 0. Restores the level systemd saved on the post-resume side. |
| `kbd-backlight-reattach.service` (system unit) | Any `modprobe -r applesmc && modprobe applesmc` cycle (an SMC userspace tool, a BCLM script) recreates the LED sysfs node. UPower keeps a stale handle to the old one and every `SetBrightness` fails with `error writing brightness`, so the Fn keys go dead and the light stays off. The udev rule starts this unit on the LED's `add` event; it restarts UPower and rewrites the saved level. |

Symptom guide:

- Light flickers with disk activity: udev rule missing.
- Light off after resume, Fn keys work: sleep hook missing.
- Light off, Fn keys do nothing, `cat /sys/class/leds/smc::kbd_backlight/brightness` is 0 while GNOME still shows a level: UPower has a stale handle. `systemctl restart upower` fixes it once; the reattach unit fixes it for good.

## Install

```bash
# login restore (user unit)
install -Dm644 kbd-backlight-restore.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable kbd-backlight-restore.service

# udev trigger override + reattach unit + resume hook (root)
sudo install -Dm644 81-macbook-kbd-backlight.rules /etc/udev/rules.d/
sudo install -Dm644 kbd-backlight-reattach.service /etc/systemd/system/
sudo install -Dm755 kbd-backlight.sleep-hook /lib/systemd/system-sleep/kbd-backlight
sudo systemctl daemon-reload
sudo udevadm control --reload
sudo udevadm trigger -s leds
```

The saved level lives in `/var/lib/systemd/backlight/platform-applesmc.768:leds:smc::kbd_backlight`
(written by `systemd-backlight@` at shutdown). Both the sleep hook and the reattach
unit read it, falling back to a fixed default if it is absent.

Note: `lid-instant-wake` also zeroes and restores the backlight around lid closes via
UPower. If the level comes back wrong after a lid close, suspect the two fighting.
