# Video Rooms – framework design

> Status: **scaffold only, nothing is built yet.** Every manifest on this
> branch says `installable: False`, so none of it can be installed by mistake.
> This document covers how the system would work, which parts are risky,
> and the questions to answer before we build it.

## 1. What we want

This is a meeting-room system that works like Zoom Rooms but joins
**other people's meetings** in Teams, Zoom, Google Meet and Webex (plus
Odoo Discuss and Jitsi Meet). It uses
each platform's **web client** as a guest, so we don't install their apps
or sign in to their systems.

| Part | Where | What it does |
| --- | --- | --- |
| **Room Console** | Tablet on the table (installed PWA) | Shows today's meetings and joins them with one tap or from a pasted link / meeting ID. Controls mic, camera, volume, sharing, layout, TV power and leaving the call. |
| **Room Display** | PC behind the TV video wall | Runs the meeting full-screen across the TVs, using the room camera, mic and speakers. Shares our screens into the call. |
| **Room Board** | Reception or corridor screen, or in Odoo | Shows the live status of several chosen rooms at once (§6f). |
| **Room Designer** | Odoo (admins) | A visual editor for each room's screens, Console layout and Presence layout (§6e). |
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

All four third-party platforms can work as browser guests. **None can be guaranteed for every
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
"no sign-in" goal. See Q3.

### Also supported: Odoo Discuss and Jitsi Meet

These two are cheap to support because we don't have to work through
someone else's interface.

| Platform | How the driver works | Effort |
| --- | --- | --- |
| **Odoo Discuss video calls** | It's our own Odoo, so calls involve no third party. The Display joins a channel's call through its invitation link as a guest. The content script is registered at runtime for our Odoo address (`chrome.scripting.registerContentScripts`), because that address differs per installation. Odoo's call UI is ours, so its selectors only change when we upgrade Odoo. | Low |
| **Jitsi Meet** | No page scraping: the Display opens Jitsi with the official **External API** (an iframe in our own display page), which gives real commands and events: mute, camera, share, layout, participants. It works for `meet.jit.si` and self-hosted Jitsi servers. | Low |

No other platforms are planned. A link from any other platform is shown
on the Console as "Not supported", and the room doesn't try to join.

## 4. Sharing our own screens

Every web client can share **a window**. So everything we share is first
shown in a window on the room PC, and the driver shares that window. A
Chromium policy (`ScreenCaptureWithoutGestureAllowedForOrigins`) plus
`--auto-select-desktop-capture-source="Video Rooms Share"` skips the
picker.

| Source | How | Phase |
| --- | --- | --- |
| **Laptop on HDMI** | A USB HDMI capture card (UVC, plug and play on Linux). The "Video Rooms Share" window shows it full-screen and the driver shares that window. | 2 (Teams MVP) |
| **Companion join** | The presenter's laptop joins the same meeting itself, muted, and shares from there. No development needed. | 2 (Teams MVP) |
| **Wireless share** | The laptop opens `https://<odoo>/video_rooms/share` and types the room's share code shown on the TVs. It streams over WebRTC (`getDisplayMedia`) to the room PC on the LAN, and is shown and shared as above. Signalling goes over Odoo. The media goes peer to peer on the LAN, or through a TURN server if guest Wi-Fi is isolated. | 6 |
| **Room PC content** | A browser window on the room PC (e.g. an Odoo record), shared the same way. | 6 |
| **In-room only** | Wireless/HDMI shown on the TVs with no call, for local presentations. It comes free with the sources above. | 6 |

## 5. Screens: configurable per room

Every installation is different. One room has a single TV, another has
two, and a boardroom may have screens on every wall. Each room's screens
are set up in the room's configuration (the room form's **Screens** tab
in Odoo). The Console's setup mode shows the same layout.

**`video.room.screen`**, one record per screen the room PC drives:

| Field | Meaning |
| --- | --- |
| Name | "Front Left", "Back Wall", … |
| Output | The PC's video output it is plugged into (`HDMI-1`, `DP-2`, …). The Node reports what it detects, so the admin chooses from that list. |
| Position | Where the screen sits, for the layout picture: which wall (front / left / right / back) and its place in a grid on that wall (column, row, width, height in cells). For example, a 2×2 front wall is four screens on the front wall at (0,0), (1,0), (0,1) and (1,1). |
| Shows | **Call**: the main meeting. Every Call screen on the same wall is **spanned as one canvas** in its grid arrangement. **Mirror**: an exact copy of another screen (e.g. side and back walls repeat the front, so everyone can see). **Shared content**: just the share, via companion mode (below). **Room info**: the idle screen, clock and next booking, even during a call. |
| Mirror Of | For Mirror: which screen it copies. |
| Physical TVs | For an output that feeds a **video wall controller**: how many TVs that output covers (information only; the controller does the splitting). |
| TV Control | How to switch the TV on and off: HDMI-CEC, RS-232 or LAN (IP), with the details per model. Optional. |

Examples:

| Room | Set-up |
| --- | --- |
| Small meeting room | 1 screen, Call. |
| Two-TV room | Two Call screens side by side on the front wall (one big canvas), **or** Call + Shared content (people left, slides right). |
| Boardroom, screens all around | A 2×2 Call wall at the front, a Mirror of it on each side wall, and Room info by the door. |
| Video wall controller | 1 output (Call, Physical TVs: 9). The controller splits it. |

**How the Display applies it:** `room_agent.py` gets the screen layout in
its sync. It then:

1. sets the outputs with `xrandr` (positions, mirrors with `--same-as`,
   spanned groups as one big desktop area);
2. places one Chrome window per group: the call window across the
   spanned Call screens, a companion window on Shared content screens,
   and the info page on Room info screens;
3. reports back what it applied and any output it can't find.

**Identify Screens** (on the room form and in the Console's setup mode)
briefly shows a big number on each TV. That makes it easy to match the
records to the real screens.

**Shared content on separate screens:** a web client draws one window,
so showing **people on some TVs and the share on others** needs one of
these:

1. **Companion mode**: a second, silent instance of the meeting (no mic,
   camera or speaker) pinned to the shared screen, on the Shared content
   screens. Meet has an official companion mode. On Teams, Zoom and Webex
   it's a second guest that the host has to admit. The room shows two
   names, e.g. "Board Room" and "Board Room (content)".
2. **SDK drivers** (later: Teams via Azure Communication Services,
   Webex, Jitsi): we draw each video stream wherever we like, with no
   second guest.

If the platform or meeting doesn't allow companion mode, Shared content
screens fall back to mirroring the main call.

## 6. Odoo side (module `video_rooms`)

| Model | Kind | Holds |
| --- | --- | --- |
| `video.room` | Primary (Rooms menu) | Name, company, capacity, Display Node, display name shown in calls ("Cliff's Country Crafts – Board Room"), default mic/camera on join, room email alias, share code. Availability (available / booked soon / in use / Do Not Disturb, computed). Do Not Disturb settings. Gets the Organisation fields automatically. |
| `meeting.meeting` (inherit) | Meeting Management | **The booking**: Room, plus the join credentials (§6b), private flag, Booked at the Door, Checked In. |
| `video.room.call` | Primary (Calls menu) | One time the room actually joined (or tried to join) a call. It links to its booking, or is ad hoc. It holds the link, the platform (detected from the link), the source, joined/left times and the outcome. Used as the call history. |
| `video.room.screen` | Room setup (Screens tab) | The room's screens and their layout (§5). |
| `video.room.platform` | Option model (Configuration) | Teams, Zoom, Meet, Webex, Odoo Discuss, Jitsi, with their link patterns, driver, notes and `active`. Starting data is `noupdate`. |
| `video.room.account` | Setup model (Configuration) | Room accounts for hosts that refuse guests (§6b). |
| `video.room.command` | Technical | The queue from the Console to the Display (join, leave, mic, camera, share, layout, volume, TV power, PTZ preset) with a status and the result. |
| `iot.node` (inherit) | IoT Interfaces | The role `video_rooms_display`, the room, the reported state (devices found, screens, driver versions). The tablets are Nodes too, with the roles `video_rooms_console` and `video_rooms_presence`, each with its restricted user (§7). |

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
  alternative if some rooms have no Display (Q22).
- **Configurable per room:** each room's configuration says which kinds
  of devices it has. One room may have **only lights**, another
  **Lighting, Air Conditioning, Blinds and Smart Window Film**. The
  Console only shows panels for what the room has.
  - **Device categories** (`video.room.ha.category`, an option model
    under Configuration, starting data `noupdate`). Each says which Home
    Assistant entity domains belong to it and how the Console draws its
    panel:

    | Category | Entities | Console panel |
    | --- | --- | --- |
    | Lighting | `light.*`, `switch.*` | On/off, brightness, all lights |
    | Air Conditioning | `climate.*`, `fan.*` | Set temperature, mode, current temperature |
    | Blinds | `cover.*` | Open, close, position |
    | Smart Window Film | `switch.*`, `light.*` (dimmable film) | Clear / Frosted, or opacity levels |
    | Scenes | `scene.*`, `script.*` | Run |

    New categories (e.g. Projector Screen, Heating) are new records,
    not code, as long as they use an existing panel type.
  - **Room Controls** (Room ▸ Room Controls tab): each control has a
    category, a name ("Ceiling Lights", "Glass Wall") and a Home
    Assistant entity.
  - **Discover Devices:** give the room its **Home Assistant Area**, and
    the Node lists that area's entities. Odoo then suggests a control for
    each one with its likely category, which you confirm or untick. Rooms
    with only lights take a minute to set up.
  - Whether a panel shows, its order and its size on the Console are set
    in the **Room Designer** (§6e).

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

### 6e. Room Designer (visual editor)

> A clickable prototype of the Room Designer and the Room Boards (sample data, nothing is saved
> to Odoo) is in `prototype/room_designer.html`. It's a page fragment: the published version
> adds the page wrapper. Use it to agree the interaction before the OWL build.

**Room Designer** is a button on the room form that opens a
full-screen visual editor (OWL client action
`video_rooms.room_designer`). It has three tabs, one for each thing a
room shows. Changes preview live, and **Publish** pushes them to the
room's screens and tablets over the bus within seconds.

**1. Screens** (the layout from §5):

```
┌ Room Designer – Board Room ─────────────── [Identify Screens] [Publish] ┐
│ Palette        │            FRONT WALL                │ Selected screen │
│ ▭ Screen       │   ┌────────┬────────┐                │ Name  Front TL  │
│ ▭ Video wall   │   │ 1 Call │ 2 Call │  ← spanned     │ Output HDMI-1 ▾ │
│   controller   │   ├────────┼────────┤    as one      │ Shows Call ▾    │
│                │   │ 3 Call │ 4 Call │    canvas      │ TV control CEC ▾│
│ Detected       │   └────────┴────────┘                │                 │
│ outputs:       │  LEFT WALL          RIGHT WALL       │                 │
│ HDMI-1 ✓       │  ┌────────┐         ┌────────┐       │                 │
│ HDMI-2 ✓ ...   │  │5 Mirror│ [table] │6 Mirror│       │                 │
│ DP-1  (free)   │  └────────┘ (▣ Console)└───────┘     │                 │
│                │        BACK WALL / DOOR: (▣ Presence)│                 │
└────────────────┴──────────────────────────────────────┴─────────────────┘
```

- It shows a top-down plan of the room, with each wall unfolded as a
  grid. Drag screens from the palette onto a wall, resize them in grid
  cells, and choose an output from the outputs the Node detected.
- Pick what each screen shows: Call, Mirror of…, Shared content or Room
  info. Screens spanned together get one outline.
- The Console and Presence tablets are placed on the plan too (on the
  table, at the door). This is for reference and for **Identify**, which
  flashes the tablet.
- It warns about problems: an output used twice, a Mirror with nothing
  to copy, more screens than the PC's outputs, a Shared content screen
  when the platform can't do companion mode.

**2. Console layout** (the Room Console tablet):

- A tablet-shaped canvas, portrait or landscape, with a grid of
  **tiles**: Join / Today's meetings, Mic, Camera, Volume, Share, Layout,
  Leave, Do Not Disturb, Camera presets, TV power. With Home Assistant
  there are also Lighting, Air Conditioning, Blinds, Smart Window Film,
  Scenes and Presets.
- Drag tiles to move them, drag their corner to resize, and drag them
  off the canvas to hide them. Tiles for things the room lacks (no Home
  Assistant, no PTZ camera) are greyed out in the palette.
- A **call page** and an **idle page** can each have their own layout,
  e.g. the call page puts Mic, Camera, Share and Leave first.
- An **Admin PIN** protects the Console's setup mode.

**3. Presence layout** (the door tablet):

- Blocks to arrange: Status (the big coloured area), Room name, Current
  booking, Time left, Today's bookings, Book Now, Do Not Disturb banner,
  Capacity, Room temperature (Home Assistant), Clock, Logo.
- Theme: the status colours (defaults: green, amber, red, purple),
  light or dark, and portrait or landscape.
- Privacy default: show booking titles or "Booked".

**How it's stored and shared:**

- The layouts are JSON on the room (`console_layout`, `presence_layout`).
  The screens are `video.room.screen` records, so they can be searched
  and reported on.
- **Layout templates** (`video.room.layout.template`, under
  Configuration) let you save a Console or Presence layout once
  ("Standard meeting room") and apply it to many rooms. A room can
  follow its template, so changing the template updates every room
  using it, or keep its own copy.
- The preview inside the editor uses the **same OWL components** as the
  real tablets, with sample data, so what you design is what appears.
- Only Video Rooms Administrators can open the designer.

### 6f. Room Boards (status of many rooms at once)

A **Room Board** is a live dashboard of several rooms at once, for a
reception screen, a corridor TV, a manager's second monitor or a tablet.

```
┌ Head Office – Meeting Rooms ─────────────────────────── 10:42 · Mon 16/11/2026 ┐
│ ┌ Board Room ──────┐ ┌ Room 2 ──────────┐ ┌ Training ────────┐ ┌ Pod A ─────┐ │
│ │ ● IN USE  →11:30 │ │ ● AVAILABLE      │ │ ● DO NOT DISTURB │ │ ● SOON     │ │
│ │ Supplier review  │ │ next 14:00       │ │ emergencies only │ │ 10:50 Sync │ │
│ │ 📹 Teams call    │ │ seats 6          │ │ until 12:00      │ │            │ │
│ └──────────────────┘ └──────────────────┘ └──────────────────┘ └────────────┘ │
│  Timeline  08 ─ 09 ─ 10 ─ 11 ─ 12 ─ 13 ─ 14 ─ 15 ─ 16 ─ 17                      │
│  Board Rm  ████████   ▓▓▓▓▓▓▓▓                ████                            │
│  Room 2                         ████████████                                  │
└───────────────────────────────────────────────────────────────────────────────┘
```

- **`video.room.board`** (Rooms ▸ Room Boards, a primary model):
  - **Rooms**: pick them one by one, *or* by rule, such as all rooms in a
    Location, Department or company. Rooms added later then appear by
    themselves.
  - **View**: Tiles, List or Timeline, or Tiles + Timeline as above.
  - The columns or tile size, sort order (name, availability, next
    booking), and what each tile shows: current booking, next booking,
    call platform, Do Not Disturb, capacity, temperature.
  - Booking titles are shown, or "Booked", following each booking's
    Private flag.
- **Where it shows:**
  - In Odoo as a dashboard (the Video Rooms app's **Overview** menu, an
    OWL client action). Live over the bus. Click a room to open it, or
    to open its Console remotely for people with Control Rooms.
  - On a wall screen at `/video_rooms/board/<id>`, full screen. That
    can be a Raspberry Pi TV as a Node (role `video_rooms_board`, page
    signed by the agent, no login), or a tablet or PC browser as a
    browser Node with its own restricted user and rolling key (as in
    §7). Either way it is read-only and never shows credentials.
- **Book Now from a board** is an option for touchscreen boards. It is
  off by default, because a wall board is usually look-only.
- Each board's look (colours, logo, light or dark) can be edited in the
  Room Designer's style, and templates apply here too.
- Odoo's own dashboard app (`custom_dashboard`) can also show a "Room
  status" widget later. The Room Board is the purpose-built version.

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

### Tablet sign-in: a dedicated restricted login per tablet with a rolling key

Decision: every tablet (Console or Presence) has **its own restricted
user** and **never needs signing in again by hand**. It stays signed in
through the same rolling-key scheme the Nodes use. Each tablet is an
`iot.node` in IoT Interfaces (roles `video_rooms_console` and
`video_rooms_presence`), so the CLAUDE.md rules on pairing and keys still
hold, and nobody manages passwords or tokens.

```
 Admin: Room ▸ Tablets ▸ Add Tablet (Console / Presence)
   └─► creates the iot.node + its restricted user, shows a QR code + one-time code (24 h)
 Tablet: scans the QR → https://<odoo>/video_rooms/tablet/pair?code=…
   └─► pairs: gets its Node ID + secret, stored as a NON-EXTRACTABLE WebCrypto key in
       IndexedDB (page script can sign with it but can never read it out)
   └─► "Install app" (PWA). From then on, on every launch / session expiry / every few hours:
 Tablet ──signed (HMAC-SHA256, timestamp, Node ID)──► POST /video_rooms/tablet/v1/session
   Odoo: checks the signature, replay and the Node's role → signs the tablet in as ITS user
         (a fresh Odoo session cookie, like login_as_any_user does) → may hand back a new
         key (rolling key, every 30 days by default) → the tablet imports it and drops the old one
```

- **The restricted user** is a portal user named after the tablet ("Board
  Room – Door"), so it doesn't use an internal-user licence. It is in
  one group, *Room Console* or *Presence Screen*, and record rules limit
  it to its own room. A Presence user can never read meeting credentials
  or control anything. The user has no password, so the only way in is
  the tablet's key.
- **Fully automatic:** the session renews quietly in the background. If
  the browser drops the cookie (restart, storage cleared by the OS), the
  page signs a new session request on load. Only clearing the PWA's data
  or **Revoke Access** on the Node needs a re-pair (scan the QR again).
- **What it needs in IoT Interfaces** (a small, general addition that
  other apps can reuse, e.g. attendance kiosks or signs on tablets):
  - "browser Nodes": a JavaScript port of `iot_auth.py`'s signing using
    WebCrypto, and pairing from a web page;
  - MAC checks switched off for these roles, since a browser can't read
    its MAC address;
  - a Node linked to a user it may start sessions for.
- **Security:** the key is bound to one tablet's browser storage and
  can't be exported, every request is signed and replay-checked, the key
  rotates automatically, and revoking it is one click. The tablet is
  still a device in a public place, so its user only ever has its own
  room's rights.

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
| 1. Rooms without video | Odoo models, views and security. **Room booking** in Meeting Management (no double bookings, credentials). **Presence screens** with Book Now. **Do Not Disturb**. **Tablets as browser Nodes** with their own restricted users and rolling keys (the IoT Interfaces addition). **Room Boards**. | Medium. Plain Odoo work with no vendor risk, and it's useful straight away. |
| 2. Teams MVP | Display Node (agent, setup, Chrome extension) and the **Microsoft Teams driver**. Console with join, leave, mic, camera, volume and Do Not Disturb. HDMI share and companion join. Configurable **screens** (span, mirror, room info). Fast-poll channel. | **Largest phase**: the video framework is built here. |
| 3. Room Designer | The visual editor: screens, Console layout, Presence layout, layout templates. | Medium. Frontend work only (OWL). |
| 4. More platforms | **Zoom, Google Meet, Webex** DOM drivers, **Odoo Discuss**, **Jitsi** (External API), the driver self-test. | Medium. Each driver is small once Teams has proven the framework. |
| 5. Building | **Home Assistant** module: device categories per room, Discover Devices, presets, triggers, room state sensor. TV power (CEC/RS-232/IP). Camera PTZ presets. | Small–medium. Home Assistant's API is stable and documented. |
| 6. Extras | Invite-email parsing, check-in and auto-release, wireless share (WebRTC + TURN), Shared content screens (companion mode), room PC content share. | Medium. |
| 7. Optional | SDK drivers (Azure Communication Services for Teams, Webex SDK) for control we can rely on and our own wall layouts. Push channel (§7 option B). | Medium–large, and has running costs (ACS). |

**Cloudpepper load stays negligible** (control messages only). The cost
that matters is **maintaining the DOM drivers against vendors' UI
changes** (Teams, Zoom, Meet, Webex): plan for a small fix every few
weeks across them. Odoo Discuss and Jitsi don't have this problem.

## 11. Decisions made

| Topic | Decision |
| --- | --- |
| Platforms | Teams, Zoom, Google Meet, Webex, **plus Odoo Discuss and Jitsi**. No others. |
| First driver | **Microsoft Teams**, the one customers use most. |
| Screens | Configurable per room: any number of screens, their walls and grid positions, and span / mirror / shared content / room info (§5), set in the Room Designer (§6e). |
| Tablet sign-in | One dedicated restricted (portal) user per tablet, kept signed in automatically by a rolling key as a browser Node: no manual re-authentication (§7). |
| Home Assistant | Optional module. The device categories each room has (Lighting, Air Conditioning, Blinds, Smart Window Film, …) are configured per room (§6d). |
| Visual editor | The Room Designer for screens, Console layout and Presence layout, with templates (§6e). |
| Multi-room status | Room Boards with rooms chosen individually or by rule, in Odoo and on wall screens (§6f). |

## 12. Questions to answer before building

**Rooms and hardware**

1. How many rooms, now and later? Is it one company, or several companies
   or organisation units?
2. For the first installations: which TVs, and do they have RS-232 or
   LAN control, or only HDMI-CEC? Is there a video wall controller
   anywhere? How many outputs does each room PC need? Screens with more
   than four outputs need a second GPU or a controller.
3. Is it acceptable to have a **signed-in room account** (Google, Zoom)
   as a fallback when a host blocks anonymous guests?
4. What camera and audio are there? Is a PTZ camera wanted, and with
   presets? Is a speakerphone already in place, or do we choose one?
5. Are the room PCs new (I'd suggest Ubuntu), or existing Windows
   machines?
6. Are the tablets Android or iPad? Android with a kiosk browser is
   easier to lock down. iPad PWAs can lose their storage after weeks
   unused, which would mean re-pairing.
7. What should the Room Boards run on: Raspberry Pi TVs, existing PCs,
   or tablets?

**Using it**

8. How do meeting links usually arrive? Invite emails to a person, to a
   room mailbox, Outlook/M365 calendars, or links pasted in chat?
   (Meeting Management already has Graph API integration we could reuse.)
9. What name should the room show in calls ("Cliff's Country Crafts –
   Board Room")? What email should it give when Webex asks for one?
10. Which share sources are a must for the Teams MVP: HDMI, companion
    join or wireless?
11. Should the room join automatically at the meeting start time, or
    always need a tap on the console?
12. Is in-room presentation without a call needed?
13. Should anyone in the room be able to use the Console, with only
    setup mode behind the Admin PIN?
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
21. Room Boards: should touchscreen boards offer Book Now?

**Home Assistant**

22. Where does Home Assistant run, and can every room PC reach it on the
    LAN? Do some rooms have no Display (then we'd need a bridge Node)?
    Are the rooms already set up as Areas in Home Assistant (for
    Discover Devices)?
23. Is the smart film a simple switch (clear / frosted) or does it have
    levels?
24. Which presets and triggers are wanted (pre-cool before bookings,
    frost the glass on Do Not Disturb, room off after the last
    meeting)? Should that logic live in Odoo presets or in Home
    Assistant automations that use our room sensor?

**Scope**

25. Should we price Teams Rooms Basic with Direct Guest Join before
    building?

## 13. Scaffold on this branch

```
video_rooms/                         Odoo app (installable: False)
  DESIGN.md                          this document
  models/video_room*.py              rooms, calls, platforms, screens, boards,
                                     layout templates, accounts, commands
  models/meeting_meeting.py          room booking + join credentials
  models/iot_node.py                 Node roles: display, console, presence, board
  controllers/node_api.py            Display Node endpoints (signed)
  controllers/tablet.py              tablet pairing + rolling-key session renewal
  controllers/console.py             Console PWA routes
  controllers/presence.py            Presence screen PWA routes (+ Book Now)
  controllers/board.py               Room Board wall-screen routes
  data/                              platforms (noupdate), program sync
  static/src/console/, presence/,    PWA shells (placeholders)
    board/, designer/                Room Board + Room Designer (OWL, placeholders)
  node_programs/video_rooms_display/ the Room PC program
    iot_program.json  setup.sh  room_agent.py
    display/          idle screen + "Video Rooms Share" window
    extension/        Chrome extension: service worker + drivers
                      (teams first; zoom, google_meet, webex, odoo_discuss, jitsi)
  prototype/room_designer.html       clickable prototype: Room Designer + Room Boards
video_rooms_home_assistant/          optional: device categories, controls, presets
video_rooms_permission/              standard roles bridge (placeholder)
```
