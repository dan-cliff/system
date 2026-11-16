TODO(build): follow CLAUDE.md "Permissions":
- privileges "Rooms: <Permission>" and "Calls: <Permission>" (7 each), each with an "Allowed" group
- workflow privilege "Control Rooms" (use the Room Console)
- base user group with the ACL + deny rules; "Video Rooms" privilege with an Administrator group
- multi-company rules on video.room / video.room.call
- option model video.room.platform: read for users, full for the Administrator
- "Room Console" and "Presence Screen" groups for the tablets' screen users (DESIGN.md §7):
  the Console may control its rooms; the Presence screen may read its rooms' schedule
  (never the meeting credentials, which carry groups= on meeting.meeting) and Book Now
