#!/bin/bash
# Setup of a Video Room Display Node: run as root by the IoT Node install command
# (never by over-the-air updates). Needs Ubuntu Desktop 24.04 LTS on a PC whose video
# outputs drive the room's screens (up to four).
#
# Installs Google Chrome and the tools the Room Display uses, logs the Node user in
# automatically to a kiosk session (X11 + Openbox: the screens are arranged with
# xrandr and windows have no borders) and starts the room browser with it. The Room Display program (room_agent.py) is
# started and updated over the air by the Node agent.
#
# The install command provides: IOT_NODE_USER, IOT_NODE_HOME, IOT_LOCAL_URL,
# IOT_PROGRAM_DIR (the program's current version, kept up to date).
set -euo pipefail

say() { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

[ "$(uname -m)" = "x86_64" ] || fail "the Room Display needs a 64-bit PC (x86_64)."
[ -d /etc/gdm3 ] || fail "no desktop found: install Ubuntu Desktop 24.04 (not Server)."

say "Installing the tools the Room Display uses"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl x11-xserver-utils unclutter openbox picom cec-utils v4l-utils pulseaudio-utils \
    fonts-noto-color-emoji >/dev/null

if ! command -v google-chrome-stable >/dev/null; then
    say "Installing Google Chrome (updates come from Google's repository)"
    tmp="$(mktemp -d)"
    curl -fsSL -o "$tmp/chrome.deb" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    apt-get install -y -qq "$tmp/chrome.deb" >/dev/null
    rm -rf "$tmp"
fi

say "Setting Chrome's room policies"
mkdir -p /etc/opt/chrome/policies/managed
cat > /etc/opt/chrome/policies/managed/video_rooms.json <<'JSON'
{
    "AudioCaptureAllowedUrls": ["https://teams.microsoft.com", "https://teams.live.com", "https://[*.]zoom.us",
        "https://meet.google.com", "https://[*.]webex.com", "https://meet.jit.si", "http://127.0.0.1:8099"],
    "VideoCaptureAllowedUrls": ["https://teams.microsoft.com", "https://teams.live.com", "https://[*.]zoom.us",
        "https://meet.google.com", "https://[*.]webex.com", "https://meet.jit.si", "http://127.0.0.1:8099"],
    "ScreenCaptureWithoutGestureAllowedForOrigins": ["https://teams.microsoft.com", "https://teams.live.com",
        "https://app.zoom.us", "https://meet.google.com", "https://web.webex.com", "https://meet.jit.si"],
    "AutoplayAllowed": true,
    "DefaultNotificationsSetting": 2,
    "PasswordManagerEnabled": false,
    "TranslateEnabled": false,
    "BrowserSignin": 0,
    "SyncDisabled": true,
    "PromptForDownloadLocation": false,
    "HardwareAccelerationModeEnabled": true,
    "MetricsReportingEnabled": false
}
JSON

say "Using an X11 kiosk session (Openbox): screens arranged with xrandr, windows without borders"
if [ -f /etc/gdm3/custom.conf ]; then
    sed -i 's/^#\?\s*WaylandEnable=.*/WaylandEnable=false/' /etc/gdm3/custom.conf
    grep -q '^WaylandEnable=false' /etc/gdm3/custom.conf || sed -i '/^\[daemon\]/a WaylandEnable=false' /etc/gdm3/custom.conf
    say "Logging $IOT_NODE_USER in automatically"
    sed -i '/^AutomaticLoginEnable=/d; /^AutomaticLogin=/d' /etc/gdm3/custom.conf
    sed -i "/^\[daemon\]/a AutomaticLoginEnable=true\nAutomaticLogin=$IOT_NODE_USER" /etc/gdm3/custom.conf
fi

say "Starting the room browser with the Openbox session"
mkdir -p /var/lib/AccountsService/users
if [ -f "/var/lib/AccountsService/users/$IOT_NODE_USER" ]; then
    sed -i '/^XSession=/d; /^Session=/d' "/var/lib/AccountsService/users/$IOT_NODE_USER"
else
    printf '[User]\n' > "/var/lib/AccountsService/users/$IOT_NODE_USER"
fi
sed -i '/^\[User\]/a XSession=openbox\nSession=openbox' "/var/lib/AccountsService/users/$IOT_NODE_USER"
OB="$IOT_NODE_HOME/.config/openbox"
mkdir -p "$OB"
cat > "$OB/autostart" <<AUTOSTART
# Video Room Display (written by its setup.sh)
picom --backend xrender &
$IOT_PROGRAM_DIR/room_browser.sh &
AUTOSTART
# No window borders or title bars, and no shortcuts that could close the room's windows.
cat > "$OB/rc.xml" <<'RC'
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <applications><application class="*"><decor>no</decor></application></applications>
  <keyboard></keyboard>
  <mouse></mouse>
  <desktops><number>1</number></desktops>
</openbox_config>
RC
chown -R "$IOT_NODE_USER":"$(id -gn "$IOT_NODE_USER")" "$IOT_NODE_HOME/.config"

say "Letting the Node user reach the camera, HDMI capture and serial TV control"
usermod -aG video,dialout "$IOT_NODE_USER" || true

say "Done. Restart the PC to start the Room Display: sudo reboot"
