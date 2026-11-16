# Video Rooms – framework design

> Status: **scaffold only, nothing is built yet.** Every manifest on this
> branch says `installable: False`, so none of it can be installed by mistake.
> This document covers how the system would work, which parts are risky,
> and the questions to answer before we build it.

## 1. What we want

This is a meeting-room system that works like Zoom Rooms but joins
**other people's meetings** in Teams, Zoom, Google Meet and Webex. It uses
each platform's **web client** as a guest, so we don't install their apps
or sign in to their systems.

| Part | Where | What it does |
| --- | --- | --- |
| **Room Console** | Tablet on the table (installed PWA) | Shows today's meetings and joins them with one tap or from a pasted link / meeting ID. Controls mic, camera, volume, sharing, layout, TV power and leaving the call. |
| **Room Display** | PC behind the TV video wall | Runs the meeting full-screen across the TVs, using the room camera, mic and speakers. Shares our screens into the call. |
| **Room Presence screen** | Tablet at the door (installed PWA) | Shows a big, clear **Available / Booked Soon / In Use / Do Not Disturb** status, today's bookings and **Book Now**. |
| **Video Rooms app** | Odoo (Cloudpepper) | Holds the rooms, the platforms, call history and permissions. **Bookings are Meeting Management meetings**, and they hold what the room needs to join an external meeting. Carries commands between the Console and the Display. |
| **Home Assistant** (optional) | Building management on the LAN | Controls the room's lights, A/C, blinds and smart privacy film from the Console and from presets. The Display Node talks to it locally. |

**Media never goes through Odoo.** Video and audio flow directly
between the room PC and the platform's cloud. Odoo only carries small
control messages, so the load on Cloudpepper stays tiny.

## 2. The key constraint (why the Display can't be "just a PWA")

A web page can't control another site's page. That's the browser's
same-origin policy. Our PWA can't click "Mute" inside
`teams.microsoft.com`. The platforms also refuse to run inside an iframe
(`X-Frame-Options` / CSP `frame-ancestors`), so we can't embed them in our
own page either.

So the Room Display is **a managed Chromium kiosk plus our own browser
extension**, run by a Node agent:

```
                 Odoo (Cloudpepper)  ── Video Rooms app
                 ▲             ▲
   HTTPS (Odoo   │             │ HTTPS, signed by the Node agent
   session + bus)│             │ (IoT Interfaces rolling key)
                 │             │
┌──────────────┐ │   ┌─────────┴─────────────────────────────────────────┐
│ Room Console │─┤   │ Room PC  = IoT Node, role "video_rooms_display"   │
│ tablet PWA   │ │   │                                                   │
└──────────────┘ │   │  iot-node agent ── room_agent.py (entrypoint)     │
┌──────────────┐ │   │                     │  · syncs commands/state     │
│ Presence     │─┘   │                     │  · OS control: audio, TVs   │
│ door tablet  │     │                     │    (CEC/RS-232/IP), PTZ,    │
└──────────────┘     │                     │    display layout           │
                     │                     │  · Home Assistant REST/WS ──┼──► Home Assistant
                     │                     │    (optional, LAN only)     │    lights · A/C ·
                     │                     │  · local WebSocket ▼        │    blinds · glass
                     │  Chromium (kiosk, managed policies)               │
                     │   └─ Video Rooms extension                        │
                     │       ├─ service worker  ◄── commands             │
                     │       └─ content scripts = platform DRIVERS       │
                     │           teams.js zoom.js google_meet.js webex.js│
                     │           (click/keyboard the web client, report  │
                     │            state: joined, muted, sharing, lobby…) │
                     └───────────────┬───────────────────────────────────┘
                                     │ HDMI ×N (or one 4K out → wall controller)
                                  TV video wall
                          camera + speakerphone (USB)
```

Why use an extension and not Playwright/Puppeteer: browsers controlled
through WebDriver/CDP automation set `navigator.webdriver`, and Google
Meet (and sometimes Zoom) refuse or challenge those browsers. Content
scripts in a normal Chromium profile look like a person using Chrome. The
Python agent still handles what a page can't, such as audio devices, TV
power and restarting the browser.

### Platform drivers

Every platform implements the same driver interface
(`node_programs/video_rooms_display/extension/drivers/driver_base.js`):

| Method | Notes |
| --- | --- |
| `join({url, displayName, mic, camera})` | Gets through the pre-join screen ("Continue on this browser", name, devices) and waits in the lobby. |
| `leave()` | |
| `setMic(on)` / `setCamera(on)` | DOM button first, keyboard shortcut as a fallback. |
| `startShare(source)` / `stopShare()` | The source is a window title (see §4). |
| `setLayout(name)` | Gallery / speaker / share-focus, where the client allows it. |
| `getState()` | `idle, prejoin, lobby, in_call, ended, error` plus mic, camera, share, participants (if visible) and the error text. |

The DOM selectors are kept in `selectors.json` (data, not code). When a
vendor changes its UI, we release a new program version and every room
updates over the air within a minute (IoT Interfaces OTA, with automatic
rollback). Each driver also includes a **self-test** that Odoo can run
from the room form, so we notice a breakage before a customer call does.

## 3. Platform by platform

All four can work as browser guests. **None can be guaranteed for every
meeting**, because the host's settings decide whether a browser guest is
let in.

| Platform | Browser guest, no sign-in | Host settings that block us | Driver risk | Optional SDK route (later) |
| --- | --- | --- | --- | --- |
| **Microsoft Teams** | Yes (Chrome/Edge, including Linux), after "Continue on this browser". Teams free (`teams.live.com`) too. | The tenant has turned off anonymous join, or the lobby is never opened. | Medium: the UI changes often. | **Azure Communication Services** can join any Teams meeting as an anonymous user. It gives full control and **our own layout** (people on one TV, the share on another). Paid per participant-minute. |
| **Zoom** | Yes, through the web client (`app.zoom.us/wc/join/…`). | The host turned off "join from browser" or requires signed-in users. The web client sometimes shows a CAPTCHA to anonymous joins. | **Highest**: the CAPTCHA can't be automated, and we shouldn't try to get around it. | Meeting SDK for Web. Zoom keeps tightening the rules for SDK apps joining meetings outside the app's own account, so check the current policy before choosing this route. |
| **Google Meet** | Yes in Chrome: "Ask to join", then someone in the meeting admits us. | A Workspace org only allows signed-in or internal users. | Medium-high: it detects automated browsers (the extension approach avoids this). | **None.** No SDK joins Meet with full media, so the web client is the only route. |
| **Cisco Webex** | Yes: the web app asks for a name and email only. | The site requires sign-in. | Medium. | **Webex Browser SDK** with a guest issuer / service app. Workable, and free to develop with. |

**Verdict:** we can work with all four. Zoom is the most likely to fail
on a given meeting (CAPTCHA, host settings). Google Meet can only ever use
the web-client route. The fallback for every platform is a **free room
account** signed in on the room PC (a Google account, a Zoom Basic
account). That gets past "signed-in users only" rules, at the cost of the
"no sign-in" goal. See Q4.

### Other platforms worth supporting

| Platform | Why | Effort |
| --- | --- | --- |
| **Odoo Discuss video calls** | Already in our Odoo. Internal and customer calls with no third party, and we control both ends. | Low |
| **Jitsi Meet** | Open source. Its official iframe API gives full control without DOM scraping. | Low |
| **GoTo Meeting** | Still common with some customers. Browser guest join works. | Medium (DOM driver) |
| **RingCentral Video** | Browser guest join works. | Medium |
| **Whereby** | Browser-first and embeddable. | Low |
| **Zoho Meeting** | Only if customers use Zoho. | Medium |

Not worth it: Skype (retired May 2025), BlueJeans (retired 2024), Amazon
Chime (retired 2026) and Slack Huddles (no guest web join). They are in
the platform data as archived records with a note, so we can tell a link
from them apart from an unknown one.

## 4. Sharing our own screens

Every web client can share **a window**. So everything we share is first
shown in a window on the room PC, and the driver shares that window. A
Chromium policy (`ScreenCaptureWithoutGestureAllowedForOrigins`) plus
`--auto-select-desktop-capture-source="Video Rooms Share"` skips the
picker.

| Source | How | Phase |
| --- | --- | --- |
| **Laptop on HDMI** | A USB HDMI capture card (UVC, plug and play on Linux). The "Video Rooms Share" window shows it full-screen and the driver shares that window. | 1 |
| **Companion join** | The presenter's laptop joins the same meeting itself, muted, and shares from there. No development needed. | 1 |
| **Wireless share** | The laptop opens `https://<odoo>/video_rooms/share` and types the room's share code shown on the TVs. It streams over WebRTC (`getDisplayMedia`) to the room PC on the LAN, and is shown and shared as above. Signalling goes over Odoo. The media goes peer to peer on the LAN, or through a TURN server if guest Wi-Fi is isolated. | 3 |
| **Room PC content** | A browser window on the room PC (e.g. an Odoo record), shared the same way. | 2 |
| **In-room only** | Wireless/HDMI shown on the TVs with no call, for local presentations. It comes free with the sources above. | 2–3 |

## 5. The video wall

A web client draws **one window**, so the simplest wall is one 4K output
from the PC into a **video wall controller** that splits it across the TVs.
The browser just goes full-screen. The alternative is a GPU with one
output per TV, with the desktop spanned as one big screen and Chromium
sized to cover it.

Showing **people on some TVs and the share on others** isn't possible
inside a single web client. Two ways round it:

1. **Join twice**: a second, silent "companion" instance (no mic, camera
   or speaker) pinned to the shared screen on the other TVs. Meet has an
   official companion mode. On Teams, Zoom and Webex it's a second guest
   that the host has to admit.
2. **SDK drivers** (Teams via ACS, Webex): we draw each video stream
   wherever we like.

## 6. Odoo side (module `video_rooms`)

| Model | Kind | Holds |
| --- | --- | --- |
| `video.room` | Primary (Rooms menu) | Name, company, capacity, Display Node, display name shown in calls ("Cliff's Country Crafts – Board Room"), default mic/camera on join, room email alias, share code. Availability (available / booked soon / in use / Do Not Disturb, computed). Do Not Disturb settings. Gets the Organisation fields automatically. |
| `meeting.meeting` (inherit) | Meeting Management | **The booking**: Room, plus the join credentials (§6b), private flag, Booked at the Door, Checked In. |
| `video.room.call` | Primary (Calls menu) | One time the room actually joined (or tried to join) a call. It links to its booking, or is ad hoc. It holds the link, the platform (detected from the link), the source, joined/left times and the outcome. Used as the call history. |
| `video.room.platform` | Option model (Configuration) | Teams, Zoom, Meet, Webex, … with their link patterns, driver, notes and `active`. Starting data is `noupdate`. |
| `video.room.account` | Setup model (Configuration) | Room accounts for hosts that refuse guests (§6b). |
| `video.room.command` | Technical | The queue from the Console to the Display (join, leave, mic, camera, share, layout, volume, TV power, PTZ preset) with a status and the result. |
| `iot.node` (inherit) | IoT Interfaces | The role `video_rooms_display`, the room, the reported state (devices found, screens, driver versions). |

### 6a. Room booking (Meeting Management)

Rooms are booked in our own **Meeting Management** app
(`meeting_management`; Video Rooms depends on it). A meeting with a
**Room** is a booking:

- Picking a room fills in the meeting's Location. Overlapping bookings of
  the same room are refused, except cancelled ones.
- Meeting Management's own Teams meetings (Graph API) join with their
  `teams_join_url` directly.
- At the start time, the room joins automatically if the room has Auto
  Join, or shows **Join** on the Console. Either way it creates a
  `video.room.call` linked to the booking.
- **Book Now** on the Presence screen creates a meeting from now. It is
  15, 30 or 60 minutes long, shortened to end at the next booking, and
  marked *Booked at the Door*.
- **Check-in** (optional, Q19): nobody checks in on the Console or
  Presence screen within N minutes, and the booking is released, so ghost
  bookings don't block the room.

**How external meeting links reach a booking:**

1. **Typed or pasted** on the meeting form (the normal way: the person
   booking adds the customer's link).
2. **Invite email.** The customer invites the room's email alias (e.g.
   `boardroom@…`). Odoo reads the `.ics` file and the body, picks out the
   link and creates or updates the booking.
3. **Console.** For ad-hoc calls: paste a link, or type a meeting ID and
   passcode. The driver builds the URL (Zoom ID+passcode, Teams meeting
   ID+passcode, Meet code, Webex number+site).
4. **"Send to Room"** from any Odoo record holding a link. A QR code on the
   idle screen also opens that page on a phone.

### 6b. Credentials for joining external meetings

The booking holds what the room needs to get into the customer's meeting:

| Field | Example |
| --- | --- |
| External Meeting Link | `https://us02web.zoom.us/j/81234567890?pwd=…` |
| Platform | Detected from the link, and can be changed. |
| Meeting ID / Passcode | For invites that give an ID and passcode instead of a link. |
| Joining Notes | "Webex site acme.webex.com", "PIN 1234#", "Ask Sam to admit us" |
| Sign In As | A **room account**, only when the host refuses guests. |

- **Who sees them:** the credential fields have `groups=` set to the Calls
  privileges. Presence screens never receive them, and nor does anyone
  who can only see the room's schedule. The Display gets them **only
  inside the join command**, over the signed Node channel, and doesn't
  keep them after the call.
- **Room accounts** (`video.room.account`) are for "signed-in users only"
  hosts. I recommend **not storing platform passwords in Odoo**. Instead,
  sign in once on the Room Display (from the Console's "Room Accounts"
  screen, which mirrors the TV). Chrome keeps the session, and Odoo keeps
  only the login name and when it was last seen signed in. If passwords
  must be kept (Q16), use an encrypted field with
  `groups='base.group_system'`, the same way IoT Interfaces keeps Node
  secrets. It would be sent only in a sign-in command.

### 6c. Room Presence screens and Do Not Disturb

The **Presence screen** is a PWA on a tablet at each room's door,
served by Odoo at `/video_rooms/presence/<room>`. It updates live over
the Odoo bus.

```
┌──────────────────────────────────────────────┐
│  BOARD ROOM                       10:42      │
│ ┌──────────────────────────────────────────┐ │
│ │        ● IN USE  until 11:30             │ │   green  = Available
│ │        Supplier review (or "Booked")     │ │   amber  = Booked Soon (≤10 min)
│ └──────────────────────────────────────────┘ │   red    = In Use
│  ⛔ DO NOT DISTURB – emergencies only        │   purple banner = Do Not Disturb
│     "Interview in progress"                  │
│  Today:  09:00 Stand-up · 10:30 Supplier ·   │
│          14:00 Customer call (Teams)         │
│  [ Book Now: 15 · 30 · 60 min ]  (free only) │
└──────────────────────────────────────────────┘
```

- The whole screen takes the status colour, so it can be read from down
  the corridor. The room name, the time left and the next booking are in
  large text.
- **Private** bookings show only "Booked" with no title or organiser.
  Credentials are never shown.
- **Book Now** shows only while the room is free. It offers the room's
  durations, shortened to fit before the next booking.
- If the tablet loses its connection, the screen shows the last known
  state greyed out with "Offline since 10:40". It never shows a stale
  "Available".

**Do Not Disturb** is set from the **Room Console** (one large toggle):

- It has two states: **Disturb OK** and **Do Not Disturb – emergencies
  only**, with an optional message ("Interview in progress").
- It lasts until the end of the current booking or call, for a chosen
  time (30 / 60 min), or until turned off. It clears automatically so it
  is never left on all day.
- **Do Not Disturb During Calls** (room setting) switches it on
  automatically while the room is in a call.
- The door shows a full-width purple banner, on top of the In Use status.
  The TVs' idle screen and the Console show it too.
- Changes are tracked in the room's chatter (who set it, when).
- With Home Assistant, a preset can follow it, e.g. frost the privacy
  glass (§6d).

### 6d. Home Assistant (optional: `video_rooms_home_assistant`)

This module is for when **Home Assistant** runs the building. It is an
optional module, not auto-installed. Video Rooms works without it.

- **Connection:** the **Room Display Node** calls Home Assistant on the
  local network (REST, or its WebSocket for live state). It uses a
  **long-lived access token** of a dedicated Home Assistant user. Odoo
  never connects to Home Assistant, as the Node rule in CLAUDE.md
  requires. The token is kept on the Node record
  (`groups='base.group_system'`) and handed to the Node in its signed
  sync. It isn't a Node credential: the Node still uses the rolling key
  with Odoo. A building-wide **Home Assistant bridge Node** role is the
  alternative if some rooms have no Display (Q21).
- **Room Controls** are Home Assistant entities listed on the room. The
  kind of control comes from the entity's domain, so no extra choice
  field is needed:

  | Entity | Console control |
  | --- | --- |
  | `light.*` | On/off and brightness |
  | `climate.*` | Set temperature, mode, current temperature |
  | `cover.*` | Blinds: open, close, position |
  | `switch.*` | e.g. **smart privacy film**: Clear / Frosted |
  | `fan.*`, `scene.*`, `script.*` | On/off, run |

- **Room Presets** do several things at once with one tap. Examples:
  - **Meeting**: lights 80%, blinds half, glass clear.
  - **Presentation**: lights 30%, blinds closed, glass frosted.
  - **Room Off**.

  Presets can also run on a **trigger**:
  - a call starts or ends;
  - a booking starts, optionally N minutes early to pre-cool or pre-heat;
  - a booking ends and the room is empty;
  - Do Not Disturb turns on or off.
- **Room state in Home Assistant:** the Node publishes
  `sensor.video_room_<room>`, which says whether the room is available,
  in use, in a call or on Do Not Disturb, plus the next booking. Home
  Assistant's own automations can use it, for example for occupancy-based
  HVAC or a corridor light. The building logic can stay in Home Assistant
  where the facilities team already works.
- **Presence screen** extras: optionally show a control's state at the
  door, e.g. the room temperature.
- **Latency:** commands use the same Console → Display channel (§7). If
  the Node is offline, the Console greys the controls out. Home Assistant
  and wall switches keep working regardless.

**Following our conventions:**

- Permissions follow CLAUDE.md, with the bridge `video_rooms_permission`.
  The privileges are Rooms and Calls (the seven CRUD privileges each),
  plus a **Control Rooms** workflow privilege for console users.
- There are Reports and Configuration menus.
- `company_id` and the Organisation fields are there.
- Dates are shown numerically.
- The app icon follows `docs/icon_style/`.
- The organiser on a call can be remapped through
  `advanced_accounts_video_rooms` later.
- No AI features are planned, so the AI rules don't apply.

## 7. The Console ↔ Display channel (latency)

Pressing **Mute** has to take effect in well under a second. The IoT
Interfaces agent only forwards normal request/response HTTP calls (30 s
timeout), and Nodes check in every 30 s, which is far too slow for
controls.

| Option | Latency | Cost |
| --- | --- | --- |
| **A. Fast poll**: `room_agent.py` polls `/video_rooms/node/v1/sync` every ~1 s during a call or while the console is awake, and every ~10 s when idle. It sends the state and gets pending commands back. The Console gets state over the normal Odoo bus. | ~1 s | Simplest. About 1 request/s per busy room, which is cheap but shows up in logs. |
| **B. Push channel in IoT Interfaces**: a long-lived signed WebSocket from the agent to Odoo's `/websocket` (gevent) worker. | <200 ms | A general IoT Interfaces upgrade (other roles benefit), but a real piece of work in a security-critical module. |
| **C. LAN direct**: the tablet talks to the room PC on the local network. | <100 ms | Needs local pairing and security. A plain-HTTP LAN page can't be an installable PWA (it isn't a secure context). |

**Recommendation:** build A first, so the work isn't blocked on B. Move
to B if A feels sluggish or other Node roles need push too.

**Tablet sign-in (Console and Presence screens).** Both are Odoo-served
PWAs, so they're installable and secure contexts with bus updates. Each
tablet stays signed in as its own **screen user**. That user only has
Control Rooms (Console), or "view schedule + Book Now" (Presence), for
its room. Using *portal* users avoids paying for internal users. The
alternative for the door is a **Raspberry Pi touchscreen as a Node**
(role `video_rooms_presence`), whose page is signed by the agent with no
login at all, fully within the Node rules. It costs a bit more hardware
per door and needs no accounts (Q13).

## 8. Room PC (Display Node) setup

- **OS: Ubuntu Desktop 24.04 LTS.** The IoT Interfaces installer (bash,
  apt, systemd) works on it unchanged. Windows would need a new installer.
- **Google Chrome .deb**, not the Ubuntu Chromium snap, because the snap
  makes managed policies and extension force-install fiddly. Policies go
  in `/etc/opt/chrome/policies/managed/video_rooms.json`: auto-grant
  camera/mic/screen capture for the four platforms, force-install our
  extension, kiosk start page = the agent's local address.
- The program's `setup.sh` (run as root by the install command) does the
  following:
  - installs Chrome and its policies;
  - sets up auto-login and kiosk autostart;
  - installs `cec-utils` and `v4l-utils`;
  - turns off screen blanking.
- Updates to the drivers and agent arrive over the air. Only a change to
  `setup.sh` needs the install command run again.

## 9. Risks

1. **Vendors change their web UIs** with no notice, which breaks drivers.
   This is the main *ongoing* cost. We limit it with selectors kept as
   data, OTA releases, the self-test, driver error reports sent to Odoo,
   and keyboard-shortcut fallbacks.
2. **Host settings** that block browser guests. Nothing we build gets past
   this. The answer is the room-account fallback, or asking the host.
3. **Zoom CAPTCHA** on anonymous web joins. Someone at the console solves
   it on the TV with the tablet as a touchpad, or we use a signed-in room
   account.
4. **Terms of service**: automating a client so that we ourselves can
   attend is low risk, but it isn't explicitly allowed. Have a look
   before relying on it commercially.
5. **Echo and audio quality** depend on the hardware: use a speakerphone
   or soundbar with built-in echo cancellation.

### Build-or-buy check

**Microsoft Teams Rooms** has a free "Basic" licence for a small number of
rooms. With *Direct Guest Join* it can join Zoom and Webex meetings
(support for Meet varies). It needs certified hardware, which costs more
than a PC and a tablet. Price it before committing; it may make this
project unnecessary, or confirm it's worth building.

## 10. Phases and effort

| Phase | Scope | Size |
| --- | --- | --- |
| 1. MVP | Odoo models, views and security. Console with join, leave, mic, camera and volume. Display Node with the agent, extension and **one** driver (Teams or Meet). HDMI share. Fast-poll channel. | Largest phase: the framework is built here. |
| 2 | The other three drivers, the self-test, room PC content share, layouts, TV power (CEC/IP), camera PTZ presets. | Medium. Each driver is small once the framework exists. |
| 1b | **Room booking** (Meeting Management room field, no double booking, credentials), **Presence screens** with Book Now, **Do Not Disturb**. | Small–medium. Plain Odoo work with no vendor risk, so it can come **first**, even before any video. |
| 2b | **Home Assistant**: controls, presets, triggers, room state sensor. | Small–medium. Home Assistant's API is stable and documented. |
| 3 | Invite-email parsing, check-in and auto-release, wireless share (WebRTC + TURN), companion "join twice" mode for split walls. | Medium. |
| 4 (optional) | SDK drivers (ACS for Teams, Webex SDK) for control we can rely on and our own wall layouts. Push channel (option B). | Medium–large, and has running costs (ACS). |

**Cloudpepper load stays negligible** (control messages only). The cost
that matters is **maintaining four DOM drivers against vendors' UI
changes**: plan for a small fix every few weeks across all of them.

## 11. Questions to answer before building

**Rooms and hardware**

1. How many rooms, now and later? Is it one company, or several companies
   or organisation units?
2. The video wall: how many TVs, how are they arranged, and what make and
   model are they? Do they have RS-232 or LAN control, or only HDMI-CEC?
   Is there a video wall controller already, or will the PC drive each
   TV?
3. Should the wall show **people and the share on different TVs**? That
   decides "join twice" or SDK drivers (§5).
4. Is it acceptable to have a **signed-in room account** (Google, Zoom)
   as a fallback when a host blocks anonymous guests?
5. What camera and audio are there? Is a PTZ camera wanted, and with
   presets? Is a speakerphone already in place, or do we choose one?
6. Is the room PC new (I'd suggest Ubuntu), or an existing Windows
   machine?
7. Is the tablet Android or iPad? Android with a kiosk browser is easier
   to lock down.

**Using it**

8. How do meeting links usually arrive? Invite emails to a person, to a
   room mailbox, Outlook/M365 calendars, or links pasted in chat?
   (Meeting Management already has Graph API integration we could reuse.)
9. What name should the room show in calls ("Cliff's Country Crafts –
   Board Room")? What email should it give when Webex asks for one?
10. Which share sources are a must for the first version: HDMI, wireless
    or companion join?
11. Should the room join automatically at the meeting start time, or
    always need a tap on the console?
12. Is in-room presentation without a call needed?
13. Should the console be usable by any staff member in the room, or need
    a PIN or login? That decides the tablet authentication (§7, option A
    needs an Odoo login per console).
14. Should call history and meeting links be kept, and for how long
    (privacy)?

**Booking, presence and Do Not Disturb**

15. Should every Meeting Management meeting be able to book a room, or
    only some meeting types? Should outside staff (e.g. an Outlook
    calendar) be able to book too?
16. Room accounts: sign in once on the Display with no password kept
    (recommended), or keep passwords encrypted in Odoo?
17. Who may see the meeting credentials: only the organiser and room
    admins, or all Video Rooms users?
18. What should the door show for a booking: title and organiser, or
    always just "Booked"? Should private be a per-booking choice?
19. Should rooms need check-in, and release the booking after how many
    minutes?
20. Who can switch off Do Not Disturb: anyone at the Console, or only
    whoever switched it on? Is a maximum length needed (e.g. 2 hours)?
    Should it come on automatically during calls?

**Home Assistant**

21. Where does Home Assistant run, and can every room PC reach it on the
    LAN? Do some rooms have no Display (then we'd need a bridge Node)?
22. Which devices are in each room, and what are their entity IDs (lights,
    A/C, blinds, privacy film)? Is the film a simple switch or does it
    have levels?
23. Which presets and triggers are wanted (pre-cool before bookings,
    frost the glass on Do Not Disturb, room off after the last
    meeting)? Should that logic live in Odoo presets or in Home
    Assistant automations that use our room sensor?

**Scope**

24. Which extra platforms from §3 should we add? I suggest **Odoo Discuss**
    and **Jitsi** (both cheap), and **GoTo** only if customers use it.
25. Should we price Teams Rooms Basic with Direct Guest Join before
    building?
26. Which platform should the MVP driver be: the one customers send most
    often?

## 12. Scaffold on this branch

```
video_rooms/                         Odoo app (installable: False)
  DESIGN.md                          this document
  models/                            field sketches + method stubs
  controllers/node_api.py            Display Node endpoints (signed)
  controllers/console.py             Console PWA routes
  controllers/presence.py            Presence screen PWA routes (+ Book Now)
  models/meeting_meeting.py          room booking + join credentials
  models/video_room_account.py       room accounts for sign-in-only hosts
  data/                              platforms (noupdate), program sync
  static/src/console/, presence/     PWA shells (placeholders)
  node_programs/video_rooms_display/ the Room PC program
    iot_program.json  setup.sh  room_agent.py
    display/          idle screen + "Video Rooms Share" window
    extension/        Chrome extension: service worker + drivers
video_rooms_home_assistant/          optional: controls, presets, Home Assistant link
video_rooms_permission/              standard roles bridge (placeholder)
```
