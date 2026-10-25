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
| **Configuration** | Status Boards, Machine Models (Brother PR1060W included), Hoops & Frames, Placements and Stabilisers. |
| **IoT Interfaces › Nodes** | The Raspberry Pis (Nodes) Embroidery uses: *Embroidery Bridges* beside the machines and *Display Screens* on TVs. |

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
* **Bridge: copy to a folder**: the machine's bridge Node saves the design
  into a folder, such as a USB stick plugged into the Node (`/media/*/*`
  uses whichever stick is mounted) or a shared network folder.
* **Bridge: simulator**: the bridge pretends to stitch the design and reports
  live progress, colour changes and a thread break. Use it to try the whole
  flow before the machine arrives.

Brother doesn't publish an API for the PR-series machines, so live stitch
counts from a real PR1060W need a driver written against whatever the
machine exposes on the network once it is here. The bridge is built for
that: a driver subclasses `Driver` in
`node_programs/embroidery_bridge/embroidery_bridge.py`, and its `tick()`
returns the same progress reports the simulator sends. Once released, it
reaches the bridge Nodes over the air.

## Nodes (IoT Interfaces)

Odoo is hosted outside the workshop network, so it can't reach the machines
or the TVs. Embroidery uses two kinds of **Node** (a Raspberry Pi on the
workshop network), set up in the **IoT Interfaces** app:

* **Embroidery Bridge** (beside the machines): collects the designs sent
  from Odoo, delivers them to its machines and reports the stitch-out
  progress back. Choose it as the **Bridge Node** on each machine.
* **Display Screen** (plugged into a TV, with Raspberry Pi OS with
  desktop): shows its **Status Board** full screen.

To add one, go to **IoT Interfaces › Nodes › Embroidery Bridges** (or
**Display Screens**), create the Node and click **Pair Node**,
then run the command it shows on the Pi. The same command builds every
Node. After that the Node keeps its own rolling key and takes program
updates over the air. See the IoT Interfaces README for security, updates
and GitHub.

Both programs ship with this module in `node_programs/` and appear under
**IoT Interfaces › Configuration › Programs**:

* `embroidery_bridge`: the bridge program and its driver settings
  (`config.json`).
* `embroidery_display`: `setup.sh`, which installs Chromium and opens the
  board full screen when the desktop starts, and `kiosk.sh`.

## Machine status boards on a TV

A **Status Board** (**Configuration › Status Boards**) sets what a wall
screen shows:

* **Machines**: which ones, in order (empty means all), and whether
  offline machines are shown.
* **Layout**: a grid of machine cards, a list with one row per machine, or
  one machine at a time (rotating, with a strip showing every machine's
  status). Also the number of columns, dark or light theme, text size,
  refresh interval and time zone.
* **What is shown**: heading, logo, clock and date, status summary; the
  current job, customer, product and pieces, assigned person and design
  preview; progress bar, stitch count, current thread colour, time
  remaining and ETA, and errors; and the machine's next jobs.

**Preview** opens the board in the browser.

A **Display Screen** Node shows one board (or, with Live Sales Counter
installed, a live sales counter). Change its board, or
anything on the board, and the screen updates within a few seconds.
**Reload Screen** on the Node makes it reload the page. Chromium on the
Node opens the Node agent's local address, which signs its requests to
Odoo, so the screen needs no Odoo login and its address holds no secret.

## API

Every route is signed by the Node agent (IoT Interfaces) and allows only
its role.

Embroidery Bridge:

* `POST /embroidery/bridge/v1/poll`, with
  `{"version": "...", "machines": [{"id": 1, "online": true, "message": "..."}]}`.
  It returns the bridge's machines, the `queued` stitch outs to deliver and
  the `open` stitch outs (`{id: state}`).
* `GET /embroidery/bridge/v1/stitchout/<id>/file` returns the `.pes` file.
* `POST /embroidery/bridge/v1/stitchout/<id>/report`, with any of
  `status` (`sent`, `stitching`, `paused`, `error`, `done`, `cancelled`),
  `stitch`, `color` (1 = first colour), `speed` (stitches per minute),
  `message`, `error_code`, and
  `events: [{"type": "info" | "error" | "color_change" | ..., "message", "code", "stitch"}]`.

Display Screen:

* `GET /embroidery/node/v1/display/page` returns the status page.
* `GET /embroidery/node/v1/display/data.json` returns what the page shows.
* `GET /embroidery/node/v1/display/design/<id>` returns a design preview.
