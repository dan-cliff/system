#!/bin/bash
# Started by the Openbox session (see setup.sh): keeps the room's Chrome running, with its
# DevTools port open on 127.0.0.1 only so room_agent.py can drive it. Updated over the
# air with the program; room_agent.py arranges the screens and windows.
PROFILE="$HOME/.config/video-room-chrome"
PORT=9222
xset s off -dpms s noblank 2>/dev/null || true
command -v unclutter >/dev/null && (unclutter -idle 1 -root &)
for _ in $(seq 1 120); do
    curl -fs -o /dev/null --max-time 2 http://127.0.0.1:8099/_node/status && break
    sleep 1
done
while true; do
    # A crash must not leave "Restore pages?" behind.
    sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"Crashed"/"exit_type":"Normal"/' \
        "$PROFILE/Default/Preferences" 2>/dev/null || true
    google-chrome-stable --user-data-dir="$PROFILE" --remote-debugging-port=$PORT --remote-debugging-address=127.0.0.1 \
        --remote-allow-origins=http://127.0.0.1:$PORT --no-first-run --noerrdialogs --disable-infobars \
        --disable-session-crashed-bubble --disable-features=Translate,MediaRouter --autoplay-policy=no-user-gesture-required \
        --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --disable-background-timer-throttling \
        --use-fake-ui-for-media-stream --auto-select-desktop-capture-source="Video Rooms Share" \
        --check-for-update-interval=31536000 --password-store=basic --start-fullscreen \
        --app=http://127.0.0.1:8099/
    sleep 3
done
