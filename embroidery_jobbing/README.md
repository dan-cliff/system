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
   "Workshop Pi"), save, and click **Generate Access Token**.
3. Copy the install command it shows and run it in a terminal on the Pi
   (or over SSH):

   ```
   curl -fsSL https://<odoo>/embroidery/bridge/install.sh | sudo bash -s -- --url https://<odoo> --token <token>
   ```

   This installs the bridge in `/opt/embroidery-bridge`, saves its settings
   in `/etc/embroidery-bridge/config.json` and starts the
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
| Update the bridge | run the install command again without `--token` |
| New token | run the install command with the new `--token` |
| Remove | `curl -fsSL https://<odoo>/embroidery/bridge/install.sh \| sudo bash -s -- --uninstall` |

Raspberry Pi OS with desktop mounts USB sticks at `/media/<user>/<label>`;
Lite doesn't mount them by itself, so on Lite use a fixed folder (or set up
automounting).

To run the bridge by hand instead, copy the `bridge` folder anywhere, copy
`config.example.json` to `config.json`, fill in the Odoo address and token,
and run `python3 embroidery_bridge.py`.

### Bridge API

The `/v1` requests send `Authorization: Bearer <token>`.

* `GET /embroidery/bridge/install.sh` and `GET /embroidery/bridge/embroidery_bridge.py`
  return the installer and the bridge (no token needed: they hold no settings).
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
