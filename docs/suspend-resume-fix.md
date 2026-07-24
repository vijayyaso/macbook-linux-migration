# Suspend/resume on a MacBookPro11,4 with an adapter-mounted NVMe SSD

The full debugging story behind the kernel parameters and the lid-wake design.
Machine: MacBookPro11,4 (i7-4980HQ, Iris Pro), Zorin OS 18.1 / Ubuntu noble,
GNOME 46 Wayland, third-party M.2 NVMe (Crucial P310) in the Apple blade-SSD slot
via a passive adapter, dual-boot with macOS (independent UEFI entries — GRUB
changes never touch macOS).

## Problem 1: resume hangs (fixed)

**Symptoms:** opening the lid sometimes did nothing; sometimes keys/power button
didn't help and only a hard power-cycle recovered the machine.

**Root cause:** the NVMe controller behind the adapter threw thousands of
IOMMU/DMAR faults during resume (`DMA Write NO_PASID … non-zero reserved fields
in PTE`), on top of NVMe APST putting the drive into idle states it couldn't
wake from behind the adapter.

**Fix** in `/etc/default/grub`, then `update-grub`:

```
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash intel_iommu=off nvme_core.default_ps_max_latency_us=0"
```

Verified: zero DMAR faults across many suspend cycles, kernel resume in well
under a second.

## Problem 2: lid wake takes ~5s, wanted instant (worked around)

Measured budget for a deep-sleep (S3) lid wake:

| Phase | Time | Fixable? |
|---|---|---|
| EC notices lid, powers platform | ~3s | **No** — Apple EC firmware |
| Kernel + device resume | ~1s | Already optimized |
| GNOME first frame | ~1–2s | Marginal |
| Occasional wifi/webcam firmware reloads | +0–7s | No (reverse-engineered drivers) |

Dead ends proven so the next person doesn't repeat them:

- **DSDT analysis:** `LID0._PRW` declares GPE 0x23; the EC query handler `_Q20`
  contains no delay code. The latency is pre-ACPI, inside the EC.
- **`acpi_osi=!Darwin`** (take the Windows/BootCamp firmware path): lid wake got
  *slower* (~10s) and USB keyboard wake broke — Apple's DSDT only arms USB wake
  on the Darwin path. Reverted.
- **s2idle (suspend-to-idle):** wake would be fast, but the EC never signals lid
  events in s2idle — not via its query GPE, not via GPE 0x23 even with the EC
  wake mask bit `EWLO` (EC offset 0x68 bit 0) set manually through `ec_sys`.
  Lid events just queue silently until another wake source fires. Charger plug
  *does* wake s2idle (GPE 0x0D, the power-button/XHC line). Keyboard wake in
  s2idle additionally needs USB root hubs armed
  (`echo enabled > /sys/bus/usb/devices/usb1/power/wakeup`, same for usb2).
- **s2idle NVMe note:** the Crucial P310 uses a host memory buffer, which forces
  the full-shutdown suspend path; the root port then burns ~1.1s on resume.
  `echo 0 > /sys/bus/pci/devices/<nvme-port>/d3cold_allowed` fixes that — only
  relevant if you use s2idle.
- **Measurement trap:** dmesg/ftrace timestamps are massively inflated during
  early resume on this machine (sched_clock skew after S3). Measure resume time
  against an `rtcwake` alarm's wall-clock time instead.

**Chosen design** (see `lid-instant-wake/`): don't sleep at all for short lid
closes — display and keyboard backlight off, instant restore on open; enter real
S3 only after 60 min closed on AC / 15 min on battery. This is what makes it
*feel* like a Mac: the everyday case is instant, the long-idle case behaves like
Mac standby (5–12s wake). Tip: tap a key right after opening the lid — USB wake
skips the EC's ~3s lid latency.

## Problem 3: open bug (unresolved, rare)

After many rapid suspend cycles in one session, a `resource_lock` read-lock
livelock can hit: multiple CPUs spin in `queued_read_lock_slowpath` via
`find_next_res → walk_system_ram_range → … → vvar_fault` right after resume.
Fan and keyboard light come on but display and all input stay dead; only a hard
reboot recovers. Suspect: a resource-tree leak in `facetimehd` or `brcmfmac`
across resumes. If you hit this: it's kernel-side, not your config.
