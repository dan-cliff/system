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
| **Configuration** | Bridges, Machine Models (Brother PR1060W included), Hoops & Frames, Placements and Stabilisers. |

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
  a folder on its PC, such as a USB stick for the machine or the folder your
  Brother software sends designs from.
* **Bridge: simulator**: the bridge pretends to stitch the design and reports
  live progress, colour changes and a thread break. Use it to try the whole
  flow before the machine arrives.

Brother doesn't publish an API for the PR-series machines, so live stitch
counts from a real PR1060W need a driver written against whatever the
machine exposes on the network once it is here. The bridge is built for
that: a driver subclasses `Driver` in `bridge/embroidery_bridge.py`, and its
`tick()` returns the same progress reports the simulator sends.

## Setting up the Embroidery Bridge

The bridge is one Python file with no dependencies. It connects out to Odoo
over HTTPS every few seconds, so nothing needs opening on the router.

1. Install Python 3.8 or newer on a PC on the machines' network
   (on Windows tick "Add Python to PATH").
2. Copy the `bridge` folder to the PC.
3. In Odoo: **Embroidery › Configuration › Bridges › New**, name it (e.g.
   "Workshop PC"), save, and click **Generate Access Token**.
4. Copy `config.example.json` to `config.json` and paste in the Odoo address
   and token.
5. On each machine (**Embroidery › Machines**) set the **Connection**, the
   **Bridge** and, for folder delivery, the **Folder on Bridge PC**.
6. Run `python embroidery_bridge.py` (Windows: `py embroidery_bridge.py`).
   The bridge shows as online in Odoo within a few seconds. To start it with
   Windows, add a Task Scheduler task "At log on" running
   `py C:\path\to\bridge\embroidery_bridge.py`.

### Bridge API

All requests send `Authorization: Bearer <token>`.

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
