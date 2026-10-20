#!/bin/bash
# Builds an IoT Node: a Raspberry Pi (or any Debian-based Linux with systemd)
# that connects Odoo to hardware on the local network.
#
# Odoo shows the exact command when you click "Pair Node" on the Node:
#
#   curl -fsSL https://<odoo>/iot/install.sh | sudo bash -s -- --url https://<odoo> --pair <code>
#
# It installs the Node agent as the iot-node service, pairs the Node with
# Odoo, downloads the program of the Node's role and runs the program's
# setup script (as root). From then on the agent keeps the Node's rolling
# key and updates the program over the air: the Node is paired once.
# Run the command again without --pair to update the agent and re-run the
# program's setup script.
#
# Options:
#   --url URL       Odoo address (required for a new install)
#   --pair CODE     one-time pairing code from Odoo
#   --user USER     account the Node's programs run as (default: the user running sudo)
#   --reboot        restart the Node at the end
#   --uninstall     remove the Node agent and its program (the key is kept)
set -euo pipefail

APP_DIR=/opt/iot-node
CONFIG_DIR=/etc/iot-node
CONFIG="$CONFIG_DIR/config.json"
STATE_DIR=/var/lib/iot-node
SERVICE=iot-node
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
    fail "pass --user with the account the Node's programs should run as."
fi
RUN_GROUP="$(id -gn "$RUN_USER")"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"

# Environment the program's setup and uninstall scripts get.
program_env() {
    export IOT_NODE_USER="$RUN_USER" IOT_NODE_HOME="$RUN_HOME" IOT_ODOO_URL="$URL" \
        IOT_LOCAL_URL="http://127.0.0.1:$PORT/" IOT_PROGRAM_DIR="$STATE_DIR/program" IOT_DATA_DIR="$STATE_DIR/data"
}

if [ "$UNINSTALL" -eq 1 ]; then
    systemctl disable --now "$SERVICE" 2>/dev/null || true
    if [ -x "$STATE_DIR/program/uninstall.sh" ]; then
        say "Removing the program's setup"
        program_env
        bash "$STATE_DIR/program/uninstall.sh" || true
    fi
    rm -f "$UNIT"
    systemctl daemon-reload
    rm -rf "$APP_DIR" "$STATE_DIR/programs" "$STATE_DIR/program" "$STATE_DIR/installed.json"
    say "Node agent removed. Its key is still in $STATE_DIR (revoke it in Odoo if the Node is retired)."
    exit 0
fi

command -v python3 >/dev/null || fail "Python 3 is not installed (sudo apt install python3)."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' || fail "Python 3.8 or newer is needed."
command -v systemctl >/dev/null || fail "systemd is needed to run the Node agent."
command -v curl >/dev/null || fail "curl is needed (sudo apt install curl)."

if [ -z "$URL" ] && [ -f "$CONFIG" ]; then
    URL="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("odoo_url", ""))' "$CONFIG")"
fi
[ -n "$URL" ] || fail "pass --url with your Odoo address."
if [ -z "$CODE" ] && [ ! -f "$STATE_DIR/credentials.json" ]; then
    fail "pass --pair with the pairing code from Odoo (IoT Interfaces > Nodes > Pair Node)."
fi

say "Downloading the Node agent from $URL"
mkdir -p "$APP_DIR"
# Run from the Odoo module's source: install the files beside it.
# Piped from curl: download them from Odoo.
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
fetch() {  # fetch <path on Odoo> <file beside this script> <installed name>
    if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/$2" ]; then
        cp "$SCRIPT_DIR/$2" "$APP_DIR/$3.new"
    else
        curl -fsSL "$URL/$1" -o "$APP_DIR/$3.new" || fail "could not download $1 from $URL."
    fi
    python3 -m py_compile "$APP_DIR/$3.new" || fail "the downloaded $3 is not valid Python."
    mv "$APP_DIR/$3.new" "$APP_DIR/$3"
}
fetch iot/pi/iot_node_agent.py iot_node_agent.py iot_node_agent.py
fetch iot/pi/iot_auth.py ../lib/iot_auth.py iot_auth.py
rm -rf "$APP_DIR/__pycache__"
chmod 755 "$APP_DIR/iot_node_agent.py"
chmod 644 "$APP_DIR/iot_auth.py"

say "Saving the settings in $CONFIG"
mkdir -p "$CONFIG_DIR"
python3 - "$CONFIG" "$URL" "$STATE_DIR" "$PORT" <<'PY'
import json, os, sys
path, url, state_dir, port = sys.argv[1:5]
config = {}
if os.path.exists(path):
    with open(path) as file:
        config = json.load(file)
config.update(odoo_url=url, state_dir=state_dir)
config.setdefault('port', int(port))
with open(path + '.new', 'w') as file:
    json.dump(config, file, indent=4)
os.replace(path + '.new', path)
PY
chmod 644 "$CONFIG"
# The Node's key and programs: only the Node's user can read them.
mkdir -p "$STATE_DIR"
chown "$RUN_USER":"$RUN_GROUP" "$STATE_DIR"
chmod 700 "$STATE_DIR"

agent() { runuser -u "$RUN_USER" -- python3 "$APP_DIR/iot_node_agent.py" --config "$CONFIG" "$@"; }

systemctl stop "$SERVICE" 2>/dev/null || true
if [ -n "$CODE" ]; then
    say "Pairing this Node with Odoo"
    agent --pair "$CODE" || fail "pairing failed (see above). Make a new pairing code in Odoo and run the command again."
fi

say "Installing the Node's program"
RESULT="$(agent --update-once)" || fail "could not get the Node's program from Odoo (see above)."
field() { python3 -c 'import json, sys; print(json.loads(sys.argv[1]).get(sys.argv[2]) or "")' "$RESULT" "$1"; }
PROGRAM="$(field program)"
SETUP="$(field setup)"
SETUP_SHA="$(field setup_sha256)"
[ -z "$(field error)" ] || fail "$(field error)"
if [ -z "$PROGRAM" ]; then
    say "Odoo has no program for this Node's role yet: the agent installs it when there is one."
elif [ -n "$SETUP" ]; then
    say "Running the setup of $PROGRAM"
    program_env
    (cd "$STATE_DIR/program" && bash "./$SETUP") || fail "the program's setup failed (see above)."
    agent --setup-applied "$SETUP_SHA"
fi

# Hardware access for the programs: groups that exist on this system.
HW_GROUPS=""
for group in dialout plugdev gpio i2c spi video audio input; do
    getent group "$group" >/dev/null && HW_GROUPS="$HW_GROUPS $group"
done

say "Setting up the $SERVICE service (runs as $RUN_USER)"
cat > "$UNIT" <<EOF
[Unit]
Description=IoT Node agent (Odoo IoT Interfaces)
Wants=network-online.target
After=network-online.target time-sync.target

[Service]
User=$RUN_USER
SupplementaryGroups=$HW_GROUPS
ExecStart=/usr/bin/env python3 $APP_DIR/iot_node_agent.py --config $CONFIG
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
systemctl is-active --quiet "$SERVICE" || fail "the Node agent did not start. See: sudo journalctl -u $SERVICE -n 50"
say "Done. The Node shows as online in Odoo within a minute and takes program updates over the air."
echo "Log:       sudo journalctl -u $SERVICE -f"
echo "Uninstall: curl -fsSL $URL/iot/install.sh | sudo bash -s -- --uninstall"
if [ "$REBOOT" -eq 1 ]; then
    say "Restarting the Node"
    reboot
fi
