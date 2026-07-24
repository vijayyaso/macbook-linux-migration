# Desktop optimization pass (July 2026)

Goal: close the efficiency gap with macOS on the MacBookPro11,4 — GPU offload,
background-app throttling, and pixel-perfect scaling — plus a modern
libadwaita look. Companion to [`../smooth-cursor-thermal/`](../smooth-cursor-thermal/).

## 1. Integer 2.0 display scale (was fractional ~1.75)

Fractional scaling makes Mutter render every frame at 2× then downscale —
a full-screen GPU resample per frame on a 5.2 MP panel — and XWayland apps
get upscaled blurry on top. macOS ran this panel at exactly 2×
("looks like 1440×900"). Set 2.0 in Settings → Displays (persisted in
`~/.config/monitors.xml`). Sharper *and* cheaper.

## 2. Chrome: native Wayland + VA-API H.264 decode

Chrome ≥143 enables hardware video decode by default on Wayland, but only
when actually running the Wayland backend, and the newer iHD VA-API driver
fails on Broadwell — the legacy i965 driver works. Local desktop override
(`~/.local/share/applications/google-chrome.desktop`) prefixes Exec with:

```
env LIBVA_DRIVER_NAME=i965 /usr/bin/google-chrome-stable \
  --ozone-platform-hint=auto \
  --enable-features=AcceleratedVideoDecodeLinuxGL,VaapiIgnoreDriverChecks
```

Broadwell only hardware-decodes H.264 (no VP9/AV1), so YouTube must be forced
to H.264. Managed policy `/etc/opt/chrome/policies/managed/enhanced-h264ify.json`
force-installs [enhanced-h264ify](https://chromewebstore.google.com/detail/enhanced-h264ify/omkfmpieigblcllmkgbflkikinpkodlk):

```json
{ "ExtensionInstallForcelist": ["omkfmpieigblcllmkgbflkikinpkodlk;https://clients2.google.com/service/update2/crx"] }
```

Verify at `chrome://gpu` → "Video Decode: Hardware accelerated".
Electron apps (Orca IDE, Claude Desktop) got `--ozone-platform-hint=auto`
via local `.desktop` overrides too — native Wayland means crisp at 2× and
less compositor work.

## 3. ananicy-cpp — the App Nap substitute

macOS quietly throttles background apps (App Nap, timer coalescing); Linux
doesn't, so identical workloads run hotter. `ananicy-cpp` + the CachyOS rule
set (~15,800 rules) auto-renices: compositor/interactive apps boosted,
background daemons and build jobs pushed to low priority.

Not packaged for Ubuntu/Zorin — built from source:

```bash
git clone --depth 1 https://gitlab.com/ananicy-cpp/ananicy-cpp.git
git clone --depth 1 https://github.com/CachyOS/ananicy-rules.git
cd ananicy-cpp
cmake -B build -GNinja -DCMAKE_BUILD_TYPE=Release -DUSE_BPF_PROC_IMPL=OFF \
  -DUSE_EXTERNAL_JSON=OFF -DUSE_EXTERNAL_SPDLOG=OFF -DUSE_EXTERNAL_FMTLIB=OFF
cmake --build build -j4
sudo cmake --install build            # → /usr/local/bin/ananicy-cpp
sudo cp -r ../ananicy-rules/* /etc/ananicy.d/
sudo systemctl enable --now ananicy-cpp
```

## 4. Theme: modern libadwaita look

- GTK theme: **adw-gtk3-dark** ([lassekongo83/adw-gtk3](https://github.com/lassekongo83/adw-gtk3) v6.5 → `~/.themes`)
- Icons: **MoreWaita** ([somepaulo/MoreWaita](https://github.com/somepaulo/MoreWaita) → `~/.local/share/icons`)
- Shell theme: reset to default Adwaita (`user-theme` name `''`)
- Font: Inter (already set); cursor: Adwaita (already set)
- **blur-my-shell disabled** — live blur costs seconds per frame on the
  Iris Pro at this resolution (see hardware truths in the main README)

```bash
gsettings set org.gnome.desktop.interface gtk-theme 'adw-gtk3-dark'
gsettings set org.gnome.desktop.interface icon-theme 'MoreWaita'
gsettings set org.gnome.shell.extensions.user-theme name ''
gnome-extensions disable blur-my-shell@aunetx
```

## 5. Round 2 — from community research (Arch Wiki, forums, Reddit)

- **`noatime` on the root ext4 mount** (`/etc/fstab`, was `relatime`) — stops
  metadata writes on every file read.
- **profile-sync-daemon** (`apt install profile-sync-daemon`) — keeps the
  Chrome profile in tmpfs (overlayfs mode) and syncs to disk hourly/at logout;
  snappier browser, far fewer disk writes. Config:
  `~/.config/psd/psd.conf` → `USE_OVERLAYFS="yes"`, `BROWSERS="google-chrome"`,
  plus a NOPASSWD sudoers entry for `/usr/bin/psd-overlay-helper`.
  Enabled as a user service; activates at next login (browser must not be
  running when it first starts).
- **I/O scheduler**: verified `none` on the NVMe — correct per the Arch Wiki
  (BFQ/deadline only help SATA/HDD).
- **sched-ext — DONE**: the kernel has `CONFIG_SCHED_CLASS_EXT=y`, and the
  userland comes from [`ppa:arighi/sched-ext`](https://launchpad.net/~arighi/+archive/ubuntu/sched-ext)
  (Canonical kernel engineer's backport for Noble; official archive support
  starts at Ubuntu 25.04):

  ```bash
  sudo add-apt-repository ppa:arighi/sched-ext
  sudo apt install scx
  # /etc/default/scx:  SCX_SCHEDULER=scx_lavd  SCX_FLAGS="--autopower"
  sudo systemctl enable --now scx.service
  cat /sys/kernel/sched_ext/root/ops   # → lavd_… when active
  ```

  `scx_lavd` keeps the GUI responsive at 100% CPU load (the failure mode this
  laptop hits most) and `--autopower` follows the power profile on battery.
  If it ever misbehaves the kernel watchdog ejects it back to EEVDF; swap in
  `scx_bpfland` via one word in `/etc/default/scx`. Custom kernels
  (XanMod/Liquorix) were researched and rejected: marginal gains over scx on
  the stock kernel, plus real DKMS risk to the facetimehd webcam driver.

## Already in place (verified, no action needed)

zram (7.7 G, prio 100) with swappiness 180 and `vm.page-cluster=0`; MGLRU
enabled; tracker indexing idle; Ubuntu mutter dynamic triple buffering;
undervolt −50 mV; thermald frequency-capping (no powerclamp).
