# Embroidery Jobbing

Embroidery work orders, a `.pes` design library and machine management, with a
live progress monitor for each stitch out.

## How it fits together

| Menu | What it holds |
| --- | --- |
| **Jobs** | Work orders: customer, product, pieces, item colour/sizes, placement, stabiliser, hoop, design, machine and instructions. **Send to Machine** sends the design for the next piece. |
| **Jobs › Stitch Outs** | One record per piece sent to a machine, with its progress, ETA and event/error log. |
| **Designs** | Brother `.pes` files. Stitch count, colours (Brother thread palette), size, trims and a stitch preview are read from the file on upload. |
| **Machines** | Each machine (model, needles, speed, hoops, connection) with its live status. The kanban view is the machine floor at a glance. Add more machines as the business grows. |
| **Configuration** | Bridges, Status Boards, Displays, Machine Models (Brother PR1060W included), Hoops & Frames, Placements and Stabilisers. |

The **Progress** tab on a job, machine or stitch out shows the progress bar,
stitch and colour reached, time stitching, time remaining, ETA and recent
events. It refreshes every few seconds while a stitch out is open. Operators
can Start, Pause, Report a Problem, Mark Done or Cancel from it.

The ETA uses the speed measured from the machine's reports once it has 30
seconds of stitching. Before that, or when the machine sends no live data, it
uses the machine's **Running Speed** and **Colour Change Time**.

## Getting a design to the machine

Each machine has a **Connection**:

* **Manual**: the operator downloads the `.pes` file from the job (USB stick
  or Brother's software) and presses Start / Mark Done in Odoo. The progress
  is estimated from the time spent stitching. This needs nothing installed.
* **Bridge: copy to a folder**: the Embroidery Bridge saves the design into
  a folder on its Raspberry Pi, such as a USB stick plugged into the Pi
  (`/media/*/*` uses whichever stick is mounted) or a shared network folder.
* **Bridge: simulator**: the bridge pretends to stitch the design and reports
  live progress, colour changes and a thread break. Use it to try the whole
  flow before the machine arrives.

Brother doesn't publish an API for the PR-series machines, so live stitch
counts from a real PR1060W need a driver written against whatever the
machine exposes on the network once it is here. The bridge is built for
that: a driver subclasses `Driver` in `bridge/embroidery_bridge.py`, and its
`tick()` returns the same progress reports the simulator sends.

## Setting up the Embroidery Bridge (Raspberry Pi)

The bridge is one Python file with no dependencies, made to run on a
Raspberry Pi (any model that runs Raspberry Pi OS; a Pi Zero 2 W is plenty)
beside the machines. It connects out to Odoo over HTTPS every few seconds,
so nothing needs opening on the router. It also runs on any other computer
with Python 3.8 or newer.

1. Set up the Pi with Raspberry Pi OS (Lite is fine) and connect it to the
   network the machines are on, with internet access.
2. In Odoo: **Embroidery › Configuration › Bridges › New**, name it (e.g.
   "Workshop Pi"), save, and click **Pair a Raspberry Pi**.
3. Copy the install command it shows and run it in a terminal on the Pi
   (or over SSH):

   ```
   curl -fsSL https://<odoo>/embroidery/bridge/install.sh | sudo bash -s -- --url https://<odoo> --pair <code>
   ```

   This installs the bridge in `/opt/embroidery-bridge`, pairs the Pi with
   Odoo (its key is kept in `/var/lib/embroidery-bridge`, readable only by
   the bridge's user), saves its settings in
   `/etc/embroidery-bridge/config.json` and starts the
   `embroidery-bridge` service. The service starts again whenever the Pi
   is switched on and restarts itself if it stops.
4. On each machine (**Embroidery › Machines**) set the **Connection**, the
   **Bridge** and, for folder delivery, the **Folder on Bridge**.
   The bridge shows as online in Odoo within a few seconds.

Useful commands on the Pi:

| | |
| --- | --- |
| Watch the log | `sudo journalctl -u embroidery-bridge -f` |
| Restart | `sudo systemctl restart embroidery-bridge` |
| Update the bridge | run the install command again without `--pair` |
| Pair again (new SD card, lost key) | **Pair Again** in Odoo and run the new command |
| Remove | `curl -fsSL https://<odoo>/embroidery/bridge/install.sh \| sudo bash -s -- --uninstall` |

Raspberry Pi OS with desktop mounts USB sticks at `/media/<user>/<label>`;
Lite doesn't mount them by itself, so on Lite use a fixed folder (or set up
automounting).

To run the bridge by hand instead, copy the `bridge` folder anywhere, copy
`lib/device_auth.py` beside it as `embroidery_auth.py`, copy
`config.example.json` to `config.json`, fill in the Odoo address, then run
`python3 embroidery_bridge.py --pair <code>` once and
`python3 embroidery_bridge.py` from then on.

## Machine status boards on a TV

A **Status Board** (**Configuration › Status Boards**) sets what a wall
screen shows:

* **Machines**: which ones, in order (empty means all), and whether offline
  machines are shown.
* **Layout**: a grid of machine cards, a list with one row per machine, or
  one machine at a time (rotating, with a strip showing every machine's
  status). Also the number of columns, dark or light theme, text size,
  refresh interval and time zone.
* **What is shown**: heading, logo, clock and date, status summary; the
  current job, customer, product and pieces, assigned person and design
  preview; progress bar, stitch count, current thread colour, time
  remaining and ETA, and errors; and the machine's next jobs.

**Preview** opens the board in the browser.

A **Display** (**Configuration › Displays**) is the Raspberry Pi plugged
into a TV, and the board it shows. Changing the board, or anything on it,
updates the screen within a few seconds. **Reload Screen** makes the screen
reload the page.

To set up a TV:

1. Install **Raspberry Pi OS with desktop** on the Pi, plug it into the TV
   and connect it to the network.
2. In Odoo, create the Display, choose its board and click
   **Pair a Raspberry Pi**.
3. Run the command it shows on the Pi:

   ```
   curl -fsSL https://<odoo>/embroidery/display/install.sh | sudo bash -s -- --url https://<odoo> --pair <code>
   ```

   It installs Chromium if needed and the display agent service
   (`embroidery-display`). It sets the Pi to log in to the desktop by
   itself and keep the screen on, and opens the board full screen whenever
   the Pi starts. Then restart the Pi (or add `--reboot`).

The agent serves the page to Chromium on the Pi itself
(`http://127.0.0.1:8099/`) and signs its requests to Odoo, so the screen
needs no Odoo login and its address holds no secret.

## Security

Bridges and displays are secured the same way:

* **Paired once.** **Pair a Raspberry Pi** makes a one-time pairing code,
  valid for 24 hours. The install command uses it to get the Pi's own
  device id and secret key, which the Pi keeps in a file only its service
  user can read. The code can't be used again.
* **Signed requests.** The key never travels with a request. The Pi signs
  each request with HMAC-SHA256 over the method, path, a timestamp, its MAC
  address, its device id and the body. Odoo checks the signature with its
  own copy of the key. The timestamp must be within 5 minutes of Odoo's
  clock and higher than the Pi's last one, so a captured request can't be
  replayed.
* **Keys replaced automatically.** Every **Change Key Every (days)** (30 by
  default), Odoo hands the Pi a new key in a signed response. The Pi saves
  it and switches to it, and the old key stops working once the new one is
  used. The Pi is never asked to pair again.
* **Authorised MAC addresses.** Requests and pairing are refused from a MAC
  address that isn't in the Pi's list. With **Authorise the Pi That Pairs**
  (on by default), the address of the Pi that pairs is added
  automatically, so the key only works from that Pi. Edit the list to
  allow a replacement Pi. Refused requests show under **Last Refused
  Request**.
* **Revoke Access** removes the key: the Pi is refused until it is paired
  again.

Odoo is reached over the internet, so it can't see a Pi's MAC address
itself. The Pi reports it, and it is part of what the Pi signs. That ties
the key to the paired Pi: a copied key file doesn't work on another
computer unless that computer also fakes the MAC address. The key and
HTTPS do the real protecting.

### Bridge API

The `/v1` requests are signed (see **Security** below).

* `GET /embroidery/bridge/install.sh`, `/embroidery/bridge/embroidery_bridge.py`,
  `/embroidery/display/install.sh`, `/embroidery/display/embroidery_display.py`
  and `/embroidery/pi/embroidery_auth.py` return the installers and programs
  (they hold no settings or keys).
* `POST /embroidery/pi/v1/pair`, with
  `{"code", "kind": "bridge" | "display", "mac", "macs", "hostname"}`, swaps a
  one-time pairing code for the Pi's device id and key.
* `POST /embroidery/bridge/v1/poll`, with
  `{"version": "...", "machines": [{"id": 1, "online": true, "message": "..."}]}`.
  This is the heartbeat. It returns the bridge's machines, the `queued`
  stitch outs to deliver and the `open` stitch outs (`{id: state}`).
* `GET /embroidery/bridge/v1/stitchout/<id>/file` returns the `.pes` file.
* `POST /embroidery/bridge/v1/stitchout/<id>/report`, with any of
  `status` (`sent`, `stitching`, `paused`, `error`, `done`, `cancelled`),
  `stitch`, `color` (1 = first colour), `speed` (stitches per minute),
  `message`, `error_code`, and
  `events: [{"type": "info" | "error" | "color_change" | ..., "message", "code", "stitch"}]`.
