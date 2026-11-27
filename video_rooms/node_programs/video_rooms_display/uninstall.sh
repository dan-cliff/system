#!/bin/bash
# Removes what setup.sh added (run by the IoT Node install command with --uninstall).
set -euo pipefail
rm -f "$IOT_NODE_HOME/.config/openbox/autostart" "$IOT_NODE_HOME/.config/openbox/rc.xml" \
    /etc/opt/chrome/policies/managed/video_rooms.json
sed -i '/^XSession=/d; /^Session=/d' "/var/lib/AccountsService/users/$IOT_NODE_USER" 2>/dev/null || true
if [ -f /etc/gdm3/custom.conf ]; then
    sed -i '/^AutomaticLoginEnable=/d; /^AutomaticLogin=/d' /etc/gdm3/custom.conf
fi
