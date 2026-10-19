#!/bin/bash
# Turns a Raspberry Pi plugged into a TV into an Embroidery machine status
# screen: installs the display agent as a systemd service, pairs it with
# Odoo, and opens the status board full screen in Chromium whenever the Pi
# starts. Needs Raspberry Pi OS with desktop.
#
# Odoo shows the exact command when you click "Pair a Raspberry Pi" on the Display:
#
#   curl -fsSL https://<odoo>/embroidery/display/install.sh | sudo bash -s -- --url https://<odoo> --pair <code>
#
# The Pi keeps its key from then on (Odoo replaces it from time to time on
# its own), so it is paired once. Run the command again without --pair to
# update the screen and keep its key.
#
# Options:
#   --url URL       Odoo address (required for a new install)
#   --pair CODE     one-time pairing code from Odoo
#   --user USER     desktop account that shows the screen (default: the user running sudo)
#   --reboot        restart the Pi at the end, to start the screen
#   --uninstall     remove the screen (its settings and key are kept)
set -euo pipefail

APP_DIR=/opt/embroidery-display
CONFIG_DIR=/etc/embroidery-display
CONFIG="$CONFIG_DIR/config.json"
STATE_DIR=/var/lib/embroidery-display
CREDENTIALS="$STATE_DIR/credentials.json"
SERVICE=embroidery-display
UNIT="/etc/systemd/system/$SERVICE.service"
PORT=8099

URL=""
CODE=""
RUN_USER="${SUDO_USER:-}"
UNINSTALL=0
REBOOT=0

while [ $# -gt 0 ]; do
    case "$1" in
        --url) URL="${2%/}"; shift 2 ;;
        --pair) CODE="$2"; shift 2 ;;
        --user) RUN_USER="$2"; shift 2 ;;
        --reboot) REBOOT=1; shift ;;
        --uninstall) UNINSTALL=1; shift ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

say() { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "run this with sudo."

if [ -z "$RUN_USER" ] || [ "$RUN_USER" = "root" ]; then
    RUN_USER="$(getent passwd 1000 | cut -d: -f1 || true)"
fi
if [ -z "$RUN_USER" ] || ! id "$RUN_USER" >/dev/null 2>&1; then
    fail "pass --user with the desktop account that should show the screen."
fi
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
AUTOSTART="$RUN_HOME/.config/autostart/embroidery-display.desktop"

if [ "$UNINSTALL" -eq 1 ]; then
    systemctl disable --now "$SERVICE" 2>/dev/null || true
    rm -f "$UNIT" "$AUTOSTART"
    systemctl daemon-reload
    rm -rf "$APP_DIR"
    say "Status screen removed. Its settings and key are still in $CONFIG_DIR and $STATE_DIR."
    exit 0
fi

command -v python3 >/dev/null || fail "Python 3 is not installed (sudo apt install python3)."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' || fail "Python 3.8 or newer is needed."
command -v systemctl >/dev/null || fail "systemd is needed."
if ! command -v labwc >/dev/null && ! command -v wayfire >/dev/null && ! command -v startlxde-pi >/dev/null \
        && ! command -v lxsession >/dev/null; then
    fail "no desktop found. Install Raspberry Pi OS with desktop on this Pi (not Lite)."
fi

if [ -z "$URL" ] && [ -f "$CONFIG" ]; then
    URL="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("odoo_url", ""))' "$CONFIG")"
fi
[ -n "$URL" ] || fail "pass --url with your Odoo address."
if [ -z "$CODE" ] && [ ! -f "$CREDENTIALS" ]; then
    fail "pass --pair with the pairing code from Odoo (Embroidery > Configuration > Displays > Pair a Raspberry Pi)."
fi

BROWSER="$(command -v chromium-browser || command -v chromium || true)"
if [ -z "$BROWSER" ]; then
    say "Installing Chromium"
    apt-get update -qq
    apt-get install -y -qq chromium || apt-get install -y -qq chromium-browser || fail "could not install Chromium."
    BROWSER="$(command -v chromium-browser || command -v chromium)"
fi

say "Downloading the Embroidery Display from $URL"
mkdir -p "$APP_DIR"
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
fetch() {  # fetch <name on Odoo> <local file beside this script> <installed name>
    if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/$2" ]; then
        cp "$SCRIPT_DIR/$2" "$APP_DIR/$3.new"
    else
        curl -fsSL "$URL/$1" -o "$APP_DIR/$3.new" || fail "could not download $1 from $URL."
    fi
    python3 -m py_compile "$APP_DIR/$3.new" || fail "the downloaded $3 is not valid Python."
    mv "$APP_DIR/$3.new" "$APP_DIR/$3"
}
fetch embroidery/display/embroidery_display.py embroidery_display.py embroidery_display.py
fetch embroidery/pi/embroidery_auth.py ../lib/device_auth.py embroidery_auth.py
rm -rf "$APP_DIR/__pycache__"
chmod 755 "$APP_DIR/embroidery_display.py"
chmod 644 "$APP_DIR/embroidery_auth.py"

say "Saving the settings in $CONFIG"
mkdir -p "$CONFIG_DIR"
python3 - "$CONFIG" "$URL" "$CREDENTIALS" "$PORT" <<'PY'
import json, os, sys
path, url, credentials, port = sys.argv[1:5]
config = {}
if os.path.exists(path):
    with open(path) as file:
        config = json.load(file)
config.update(odoo_url=url, credentials=credentials)
config.setdefault('port', int(port))
with open(path + '.new', 'w') as file:
    json.dump(config, file, indent=4)
os.replace(path + '.new', path)
PY
chmod 644 "$CONFIG"
mkdir -p "$STATE_DIR"
chown "$RUN_USER":"$(id -gn "$RUN_USER")" "$STATE_DIR"
chmod 700 "$STATE_DIR"

if [ -n "$CODE" ]; then
    say "Pairing this Raspberry Pi with Odoo"
    systemctl stop "$SERVICE" 2>/dev/null || true
    runuser -u "$RUN_USER" -- python3 "$APP_DIR/embroidery_display.py" --config "$CONFIG" --pair "$CODE" \
        || fail "pairing failed (see above). Make a new pairing code in Odoo and run the command again."
fi

say "Setting up the $SERVICE service (runs as $RUN_USER)"
cat > "$UNIT" <<EOF
[Unit]
Description=Embroidery Display agent (Odoo Embroidery Jobbing)
Wants=network-online.target
After=network-online.target time-sync.target

[Service]
User=$RUN_USER
ExecStart=/usr/bin/env python3 $APP_DIR/embroidery_display.py --config $CONFIG
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$STATE_DIR

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null
systemctl restart "$SERVICE"

say "Opening the status board full screen when the desktop starts"
cat > "$APP_DIR/kiosk.sh" <<EOF
#!/bin/bash
# Shows the status board full screen; restarts Chromium if it closes.
URL="http://127.0.0.1:$PORT/"
for _ in \$(seq 1 120); do
    curl -fs -o /dev/null --max-time 2 "\$URL" && break
    sleep 1
done
xset s off -dpms s noblank 2>/dev/null || true
command -v unclutter >/dev/null && (unclutter -idle 1 -root &)
while true; do
    "$BROWSER" --kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble \\
        --incognito --no-first-run --check-for-update-interval=31536000 \\
        --overscroll-history-navigation=0 --disable-pinch --password-store=basic "\$URL"
    sleep 5
done
EOF
chmod 755 "$APP_DIR/kiosk.sh"
mkdir -p "$(dirname "$AUTOSTART")"
cat > "$AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Name=Embroidery Machine Status
Exec=$APP_DIR/kiosk.sh
X-GNOME-Autostart-enabled=true
EOF
chown "$RUN_USER":"$(id -gn "$RUN_USER")" "$RUN_HOME/.config" "$(dirname "$AUTOSTART")" "$AUTOSTART"

if command -v raspi-config >/dev/null; then
    say "Logging in to the desktop automatically and keeping the screen on"
    raspi-config nonint do_boot_behaviour B4 || true
    raspi-config nonint do_blanking 1 || true
fi

sleep 2
systemctl is-active --quiet "$SERVICE" || fail "the display agent did not start. See: sudo journalctl -u $SERVICE -n 50"
say "Done. The status board opens full screen when the Pi starts."
echo "Log:       sudo journalctl -u $SERVICE -f"
echo "Uninstall: curl -fsSL $URL/embroidery/display/install.sh | sudo bash -s -- --uninstall"
if [ "$REBOOT" -eq 1 ]; then
    say "Restarting the Pi"
    reboot
else
    echo "Restart the Pi now to start the screen: sudo reboot"
fi
