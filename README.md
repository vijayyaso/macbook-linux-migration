# MacBook → Linux Migration

Configs and scripts that make a **MacBookPro11,4 (15" Retina, mid-2015)** running
**Zorin OS 18.1 (Ubuntu 24.04 base, GNOME 46, Wayland)** feel like a Mac again.
Most of it should apply to any 2013–2015 Retina MacBook Pro on any GNOME distro.

Every component was built and debugged on real hardware. Where a behavior turned
out to be impossible (Apple firmware limitations), the docs say so honestly and
describe the workaround chosen instead.

## Components

| Directory | What it does |
|---|---|
| [`lid-instant-wake/`](lid-instant-wake/) | Mac-like lid behavior: instant wake for short lid closes, real deep sleep after a battery-aware delay (60 min on AC / 15 min on battery, like macOS `standbydelay`). Also turns the keyboard backlight off while closed. |
| [`wake-veil-extension/`](wake-veil-extension/) | GNOME extension: smooth macOS-style fade-from-black when waking from deep sleep, instead of an abrupt pop-in. |
| [`three-finger-drag/`](three-finger-drag/) | macOS-style three-finger drag on the touchpad (Wayland, uinput proxy daemon). Merged in with full history from its former standalone repo. |
| [`mac-settings-extractor/`](mac-settings-extractor/) | Run on the macOS side before migrating: extracts your Mac's settings (keyboard, trackpad, power, display, behavior) into a text file so you can replicate them on Linux. Merged in with full history. |
| [`webcam-autobrightness/`](webcam-autobrightness/) | Auto screen brightness using the webcam as a light meter — the real ambient light sensor sits on the camera board and the Linux `facetimehd` driver can't read it. Samples every 5 minutes. |
| [`kbd-backlight/`](kbd-backlight/) | Restores keyboard backlight at login (GNOME zeroes it when the ambient light sensor reads 0). |
| [`docs/`](docs/) | The suspend/resume debugging story (kernel parameters that fix resume hangs, what's fixable and what's Apple-firmware-immovable) and the original fresh-install setup checklist. |

## The critical kernel parameters

If your adapter-mounted NVMe MacBook hangs on resume, this is the fix
(see [`docs/suspend-resume-fix.md`](docs/suspend-resume-fix.md) for the full story):

```
# /etc/default/grub
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash intel_iommu=off nvme_core.default_ps_max_latency_us=0"
```

then `sudo update-grub` and reboot.

- `intel_iommu=off` — third-party NVMe adapters in the Apple SSD slot throw IOMMU/DMAR
  faults during resume, which can hang the machine hard.
- `nvme_core.default_ps_max_latency_us=0` — keeps the SSD out of deep idle states it
  cannot reliably wake from behind an adapter.

## Hardware truths discovered along the way

- **Deep-sleep (S3) lid wake has a ~3s floor** before the machine even powers on —
  it's inside Apple's embedded controller and unreachable from Linux. Tested via ACPI
  table analysis, EC register pokes (`EWLO` wake mask at EC offset 0x68), and
  `acpi_osi` switching. Total wake is 5–12s depending on driver firmware reloads.
- **s2idle (light sleep) cannot wake on lid at all** — the EC stays completely silent
  about lid events until something else wakes the host. Hence the fake-sleep design.
- **Tapping a key right after opening the lid wakes faster than the lid sensor** —
  USB wake skips the EC's lid debounce.
- **`acpi_osi=!Darwin` makes things worse** on these Macs (slower lid wake, USB wake
  breaks). Linux pretending to be macOS is the good path.
- **Fullscreen live blur costs seconds per frame on the Iris Pro at 2880×1800** —
  the wake veil uses a plain fade for that reason.

## License

MIT — use freely, no warranty. These scripts poke at power management; read them
before running on your machine.
