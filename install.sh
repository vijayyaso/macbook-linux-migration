#!/usr/bin/env bash
# Installer for the three-finger-drag daemon.
# Run as your normal user: ./install.sh   (sudo is used where needed)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

echo "==> Checking dependencies"
python3 -c 'import evdev' 2>/dev/null || {
    echo "python3-evdev is missing; installing..."
    sudo apt install -y python3-evdev
}

echo "==> Granting the 'input' group access to /dev/uinput (needs sudo)"
sudo tee /etc/udev/rules.d/99-uinput-input-group.rules >/dev/null <<'EOF'
KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
EOF
echo uinput | sudo tee /etc/modules-load.d/uinput.conf >/dev/null
sudo modprobe uinput
sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=uinput

if ! id -nG "$USER" | grep -qw input; then
    echo "==> Adding $USER to the 'input' group (log out/in to take effect)"
    sudo usermod -aG input "$USER"
fi

echo "==> Installing systemd user service"
mkdir -p ~/.config/systemd/user
sed "s|%h|$HOME|g; s|ExecStart=/usr/bin/python3 .*|ExecStart=/usr/bin/python3 $HERE/three-finger-drag.py|" \
    "$HERE/three-finger-drag.service" > ~/.config/systemd/user/three-finger-drag.service
systemctl --user daemon-reload
systemctl --user enable --now three-finger-drag

echo "==> Done. Check with: systemctl --user status three-finger-drag"
