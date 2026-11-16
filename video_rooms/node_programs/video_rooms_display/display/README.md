Pages the Room Display shows outside a call (TODO(build)):

- idle screen: the program's `home` (/video_rooms/node/v1/display, served by Odoo
  through the Node agent): room name, next bookings, Do Not Disturb, the wireless
  share code and a "Send to Room" QR code.
- share.html: the "Video Rooms Share" window - full screen HDMI capture
  (getUserMedia on the capture card) or the incoming wireless share (WebRTC). The
  drivers share this window into the meeting.
