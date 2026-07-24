# webcam-autobrightness

Automatic screen brightness for 2013–2015 Retina MacBooks on Linux, using the
**webcam as a light meter**.

**Why:** on these Macs the ambient light sensor is physically on the camera
board and macOS reads it through the camera driver. The reverse-engineered
Linux `facetimehd` driver never implemented it, so every standard Linux ALS
path (`acpi-als`, `applesmc`) reads a flat 0 lux forever.

> ⚠️ Because of that stuck 0-lux sensor, **keep GNOME's built-in automatic
> brightness OFF** (`org.gnome.settings-daemon.plugins.power ambient-enabled
> false`) — with the sensor at 0 it pins the screen to minimum brightness.

**How it works:** a systemd user timer fires every 5 minutes, captures one
webcam frame with ffmpeg, computes average luma, and sets GNOME brightness via
the settings-daemon D-Bus interface. The camera LED blinks briefly on each
sample (hardwired, unavoidable).

## Install

Requires: `ffmpeg`, the `facetimehd` driver working (webcam functional).

```bash
install -Dm755 webcam-autobrightness ~/.local/bin/webcam-autobrightness
install -Dm644 webcam-autobrightness.service ~/.config/systemd/user/
install -Dm644 webcam-autobrightness.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now webcam-autobrightness.timer
```

Disable anytime: `systemctl --user disable --now webcam-autobrightness.timer`
