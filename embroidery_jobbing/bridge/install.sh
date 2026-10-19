#!/bin/bash
# Installs (or updates) the Embroidery Bridge on a Raspberry Pi, or any
# Debian-based Linux, as a systemd service that starts on boot, and pairs it
# with Odoo.
#
# Odoo shows the exact command when you click "Pair a Raspberry Pi" on the bridge:
#
#   curl -fsSL https://<odoo>/embroidery/bridge/install.sh | sudo bash -s -- --url https://<odoo> --pair <code>
#
# The Pi keeps its key from then on (Odoo replaces it from time to time on
# its own), so it is paired once. Run the command again without --pair to
# update the bridge and keep its key.
#
# Options:
#   --url URL       Odoo address (required for a new install)
#   --pair CODE     one-time pairing code from Odoo
#   --user USER     account the bridge runs as (default: the user running sudo)
#   --uninstall     stop and remove the bridge (its settings and key are kept)
set -euo pipefail

APP_DIR=/opt/embroidery-bridge
CONFIG_DIR=/etc/embroidery-bridge
CONFIG="$CONFIG_DIR/config.json"
STATE_DIR=/var/lib/embroidery-bridge
CREDENTIALS="$STATE_DIR/credentials.json"
SERVICE=embroidery-bridge
UNIT="/etc/systemd/system/$SERVICE.service"

URL=""
CODE=""
RUN_USER="${SUDO_USER:-}"
UNINSTALL=0

while [ $# -gt 0 ]; do
    case "$1" in
        --url) URL="${2%/}"; shift 2 ;;
        --pair) CODE="$2"; shift 2 ;;
        --user) RUN_USER="$2"; shift 2 ;;
        --uninstall) UNINSTALL=1; shift ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

say() { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "run this with sudo."

if [ "$UNINSTALL" -eq 1 ]; then
    systemctl disable --now "$SERVICE" 2>/dev/null || true
    rm -f "$UNIT"
    systemctl daemon-reload
    rm -rf "$APP_DIR"
    say "Embroidery Bridge removed. Its settings and key are still in $CONFIG_DIR and $STATE_DIR."
    exit 0
fi

command -v python3 >/dev/null || fail "Python 3 is not installed (sudo apt install python3)."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' || fail "Python 3.8 or newer is needed."
command -v systemctl >/dev/null || fail "systemd is needed to run the bridge as a service."

if [ -z "$RUN_USER" ] || [ "$RUN_USER" = "root" ]; then
    RUN_USER="$(getent passwd 1000 | cut -d: -f1 || true)"
fi
if [ -z "$RUN_USER" ] || ! id "$RUN_USER" >/dev/null 2>&1; then
    fail "pass --user with the account the bridge should run as."
fi

if [ -z "$URL" ] && [ -f "$CONFIG" ]; then
    URL="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("odoo_url", ""))' "$CONFIG")"
fi
[ -n "$URL" ] || fail "pass --url with your Odoo address."
if [ -z "$CODE" ] && [ ! -f "$CREDENTIALS" ]; then
    fail "pass --pair with the pairing code from Odoo (Embroidery > Configuration > Bridges > Pair a Raspberry Pi)."
fi

say "Downloading the Embroidery Bridge from $URL"
mkdir -p "$APP_DIR"
# Run from a copy of the bridge folder: install the files beside it.
# Piped from curl: download them from Odoo.
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
fetch embroidery/bridge/embroidery_bridge.py embroidery_bridge.py embroidery_bridge.py
fetch embroidery/pi/embroidery_auth.py ../lib/device_auth.py embroidery_auth.py
rm -rf "$APP_DIR/__pycache__"
chmod 755 "$APP_DIR/embroidery_bridge.py"
chmod 644 "$APP_DIR/embroidery_auth.py"

say "Saving the settings in $CONFIG"
mkdir -p "$CONFIG_DIR"
python3 - "$CONFIG" "$URL" "$CREDENTIALS" <<'PY'
import json, os, sys
path, url, credentials = sys.argv[1:4]
config = {}
if os.path.exists(path):
    with open(path) as file:
        config = json.load(file)
config['odoo_url'] = url
config['credentials'] = credentials
config.pop('token', None)
config.setdefault('poll_seconds', 10)
config.setdefault('drivers', {'folder': {}, 'simulator': {'speedup': 10, 'thread_breaks': True}})
with open(path + '.new', 'w') as file:
    json.dump(config, file, indent=4)
os.replace(path + '.new', path)
PY
chmod 644 "$CONFIG"
# The key: only the bridge's user can read it, and the bridge rewrites it
# when Odoo replaces the key.
mkdir -p "$STATE_DIR"
chown "$RUN_USER":"$(id -gn "$RUN_USER")" "$STATE_DIR"
chmod 700 "$STATE_DIR"

if [ -n "$CODE" ]; then
    say "Pairing this Raspberry Pi with Odoo"
    systemctl stop "$SERVICE" 2>/dev/null || true
    runuser -u "$RUN_USER" -- python3 "$APP_DIR/embroidery_bridge.py" --config "$CONFIG" --pair "$CODE" \
        || fail "pairing failed (see above). Make a new pairing code in Odoo and run the command again."
fi

say "Setting up the $SERVICE service (runs as $RUN_USER)"
cat > "$UNIT" <<EOF
[Unit]
Description=Embroidery Bridge (Odoo Embroidery Jobbing)
Wants=network-online.target
After=network-online.target time-sync.target

[Service]
User=$RUN_USER
ExecStart=/usr/bin/env python3 $APP_DIR/embroidery_bridge.py --config $CONFIG
Restart=always
RestartSec=10
NoNewPrivileges=true
ProtectSystem=full
ReadWritePaths=$STATE_DIR

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null
systemctl restart "$SERVICE"

sleep 3
if systemctl is-active --quiet "$SERVICE"; then
    say "The Embroidery Bridge is running. It shows as online in Odoo within a few seconds."
else
    echo "The bridge did not start. See: sudo journalctl -u $SERVICE -n 50" >&2
    exit 1
fi
echo "Log:       sudo journalctl -u $SERVICE -f"
echo "Restart:   sudo systemctl restart $SERVICE"
echo "Uninstall: curl -fsSL $URL/embroidery/bridge/install.sh | sudo bash -s -- --uninstall"
