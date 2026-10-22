#!/bin/bash
# Setup of an Embroidery Wall Display Node: run as root by the IoT Node
# install command (not by over-the-air updates). Opens the Node agent's
# local address - the display's status board - full screen in Chromium
# whenever the desktop starts. Needs Raspberry Pi OS with desktop.
#
# The install command provides: IOT_NODE_USER, IOT_NODE_HOME, IOT_LOCAL_URL,
# IOT_PROGRAM_DIR (the program's current version, kept up to date).
set -euo pipefail

say() { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

if ! command -v labwc >/dev/null && ! command -v wayfire >/dev/null && ! command -v startlxde-pi >/dev/null \
        && ! command -v lxsession >/dev/null; then
    fail "no desktop found. A wall display Node needs Raspberry Pi OS with desktop (not Lite)."
fi

if ! command -v chromium-browser >/dev/null && ! command -v chromium >/dev/null; then
    say "Installing Chromium"
    apt-get update -qq
    apt-get install -y -qq chromium || apt-get install -y -qq chromium-browser || fail "could not install Chromium."
fi

say "Opening the status board full screen when the desktop starts"
AUTOSTART="$IOT_NODE_HOME/.config/autostart/embroidery-display.desktop"
mkdir -p "$(dirname "$AUTOSTART")"
cat > "$AUTOSTART" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Embroidery Machine Status
Exec=$IOT_PROGRAM_DIR/kiosk.sh $IOT_LOCAL_URL
X-GNOME-Autostart-enabled=true
DESKTOP
chown "$IOT_NODE_USER":"$(id -gn "$IOT_NODE_USER")" "$IOT_NODE_HOME/.config" "$(dirname "$AUTOSTART")" "$AUTOSTART"

if command -v raspi-config >/dev/null; then
    say "Logging in to the desktop automatically and keeping the screen on"
    raspi-config nonint do_boot_behaviour B4 || true
    raspi-config nonint do_blanking 1 || true
fi
say "Restart the Node to start the screen: sudo reboot"
