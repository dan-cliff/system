#!/usr/bin/env python3
"""Video Room Display agent (SCAFFOLD - see video_rooms/DESIGN.md).

Started and kept running by the IoT Node agent. Reaches Odoo only through
$IOT_PROXY_URL (the Node agent signs every request; this program holds no key).

Loop:
  1. POST $IOT_PROXY_URL/video_rooms/node/v1/sync with the current state
     (~1 s during a call or while the Console is in use, ~10 s when idle).
  2. Carry out the commands that come back:
       - browser commands (join, leave, mic, camera, share, layout) -> the Video
         Rooms extension over a local WebSocket on 127.0.0.1 (browser_bridge);
       - OS commands -> volume (pactl), TV power (cec-client / RS-232 / IP),
         camera PTZ presets (v4l2-ctl), restart the browser.
  3. Report each command's result and the extension's state in the next sync.
"""
import os
import sys

PROXY = os.environ.get('IOT_PROXY_URL', 'http://127.0.0.1:8099')


def main():
    sys.exit('Video Room Display is a scaffold: not built yet (see video_rooms/DESIGN.md).')


if __name__ == '__main__':
    main()
