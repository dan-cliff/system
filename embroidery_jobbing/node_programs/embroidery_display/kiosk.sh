#!/bin/bash
# Shows the status board full screen; restarts Chromium if it closes.
# Started by the desktop (see setup.sh). Updated over the air with the program.
URL="${1:-http://127.0.0.1:8099/}"
for _ in $(seq 1 120); do
    curl -fs -o /dev/null --max-time 2 "${URL}_node/status" && break
    sleep 1
done
xset s off -dpms s noblank 2>/dev/null || true
command -v unclutter >/dev/null && (unclutter -idle 1 -root &)
BROWSER="$(command -v chromium-browser || command -v chromium)"
while true; do
    "$BROWSER" --kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble \
        --incognito --no-first-run --check-for-update-interval=31536000 \
        --overscroll-history-navigation=0 --disable-pinch --password-store=basic "$URL"
    sleep 5
done
