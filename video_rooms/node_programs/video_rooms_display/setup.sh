#!/bin/bash
# Setup of a Video Room Display Node (run as root by the IoT Node install
# command, never by over-the-air updates). SCAFFOLD - see video_rooms/DESIGN.md §8.
#
# TODO(build), on Ubuntu Desktop 24.04 LTS:
#   - install Google Chrome (.deb, not the Chromium snap)
#   - write /etc/opt/chrome/policies/managed/video_rooms.json:
#       ExtensionInstallForcelist (the Video Rooms extension, from $IOT_PROGRAM_DIR/extension),
#       VideoCaptureAllowedUrls / AudioCaptureAllowedUrls / ScreenCaptureWithoutGestureAllowedForOrigins
#       for the supported platforms, no first-run, no translate, no password manager
#   - auto-login the Node user, kiosk autostart ($IOT_PROGRAM_DIR/kiosk.sh $IOT_LOCAL_URL)
#   - apt: cec-utils (TV power over HDMI-CEC), v4l-utils (camera PTZ, HDMI capture), pulseaudio-utils
#   - no screen blanking / sleep
set -euo pipefail
echo "Video Room Display setup is not built yet (scaffold)." >&2
exit 1
