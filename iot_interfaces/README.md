# IoT Interfaces

Odoo is hosted outside our network, so it can't connect to hardware on the
local network: embroidery machines, wall screens, printers, sensors. A
**Node** does that for Odoo. A Node is a Raspberry Pi on the local network
that only ever connects *out* to Odoo over HTTPS. Nothing is opened on the
router, and Odoo never needs to find the Node.

```
Odoo (Cloudpepper)  <-- HTTPS, started by the Node --  Node (Raspberry Pi)  -- local network -->  hardware
```

Everything about the Nodes lives in this app. Other apps add a **role**
(the program a Node runs) and that role's settings.

| Menu | What it holds |
| --- | --- |
| **Nodes** | Every Node: its role, where it is, whether it is online, its program version and its security. Apps add filtered menus here (e.g. *Embroidery Bridges*). |
| **Configuration › Programs** | The code each role runs, with every version. Optionally held in GitHub. |
| **Configuration › Program Versions** | The full version history of every program. |
| **Configuration › Settings** | GitHub integration. |

## Building a Node

1. Install Raspberry Pi OS on the Pi. Use the desktop edition for screens;
   Lite is fine otherwise. Connect the Pi to the local network with
   internet access.
2. In Odoo, create the Node (**IoT Interfaces › Nodes › New**), pick its
   role and click **Pair Node**.
3. Run the command it shows on the Pi:

   ```
   curl -fsSL https://<odoo>/iot/install.sh | sudo bash -s -- --url https://<odoo> --pair <code>
   ```

The command installs the **Node agent** as the `iot-node` service, pairs
the Node, downloads its role's program and runs the program's setup script
as root. Every Node gets the same base build. The pairing code works once
and expires after 24 hours.

Useful commands on the Node:

| | |
| --- | --- |
| Watch the log | `sudo journalctl -u iot-node -f` |
| Update the agent and re-run the program's setup | the install command without `--pair` |
| Remove | `curl -fsSL https://<odoo>/iot/install.sh \| sudo bash -s -- --uninstall` |

## Security: pair once, rolling key

* **Pairing:** **Pair Node** makes a one-time pairing code. The Node swaps
  it for its own Node ID and secret key, which only the Node's service
  user can read (`/var/lib/iot-node`).
* **Signed requests:** the key never travels. The agent signs every
  request with HMAC-SHA256 over the method, path, a timestamp, its MAC
  address, its Node ID and the body. Odoo refuses unsigned requests,
  changed requests, replayed requests (timestamps must increase) and
  requests from a clock more than 5 minutes out.
* **Rolling key:** every **Change Key Every (days)** (30 by default), Odoo
  hands the Node a new key in a signed check-in. The Node switches to it,
  and the old key stops working once the new one is used. The Node is
  never paired again.
* **Authorised MAC addresses:** requests and pairing from any other MAC
  address are refused. By default the Node that pairs is authorised.
  Refused requests show under **Last Refused Request**.
* **Revoke Access** locks the Node out until it is paired again.
* **Roles:** each endpoint names the roles allowed to use it, so a screen
  Node can't use a bridge's API.

Odoo can't see a Node's MAC address over the internet. The Node reports
it as part of what it signs, which ties the key to the paired hardware.
The key and HTTPS are the real protection.

## Programs and over-the-air updates

Each role has a **program**: files plus `iot_program.json`:

```json
{
    "entrypoint": "my_program.py",
    "home": "/my_app/node/v1/page",
    "setup": "setup.sh"
}
```

* `entrypoint`: what the agent starts and keeps running (optional).
* `home`: where the agent's local address `/` opens, for screens (optional).
* `setup`: a script the install command runs as root, e.g. installing
  packages or setting up a kiosk (optional).

A program version comes from one of three places:

* **Shipped with Odoo:** the app that adds the role ships its program. A
  new version is added whenever the files change on a module update.
* **Uploaded:** **New Draft from It** on a version, edit the files, then
  **Release**.
* **GitHub:** see below.

**Updates reach the Nodes over the air.** Each Node checks in every 30
seconds. When it should run a different version, it:

1. downloads the files (skipping unchanged ones);
2. checks every file's SHA-256 and the version's checksum;
3. switches to the new version and restarts the program.

If the new version crashes 3 times within 2 minutes, the Node goes back to
the previous version and Odoo shows **Update Failed** with the reason.

* By default each released version becomes the program's **Current
  Version** (**Use Each New Version**).
* **Make Current** on an older version rolls every Node back.
* A Node can stay on a chosen version (**Updates: Stay on a chosen
  version**).
* Updates never run as root. If a version changes the `setup` script, the
  Node shows **Setup Changed**: run the install command again (without
  `--pair`) to apply it.

### GitHub

In **Settings**, turn on **GitHub** and enter a fine-grained access token
with read and write access to Contents. **Create Access Token on GitHub**
opens GitHub's new-token page with the name, description and Contents
access filled in: pick the owner and the program repositories, generate the
token and paste it into Odoo. Then give a program a
**Repository** (`owner/repo`), **Branch** and **Folder**:

* The code is managed in GitHub. Every commit to the program's folder
  becomes a version in Odoo, with its commit, author and message, so Odoo
  keeps the full history. Syncs run every 15 minutes, or immediately with
  **Sync from GitHub**.
* **Publish to GitHub** commits the current version to the folder, to
  start holding a shipped program in GitHub.
* While a program is held in GitHub, module updates don't add shipped
  versions to it.

## Adding a Node role in an app

1. Depend on `iot_interfaces` and add the role:

   ```python
   class IotNode(models.Model):
       _inherit = 'iot.node'
       role = fields.Selection(selection_add=[('myapp_reader', 'My App Reader')],
                               ondelete={'myapp_reader': 'set default'})
   ```

   Put the role's settings on `iot.node` and show them in an inherited
   form page with `invisible="role != 'myapp_reader'"`.

2. Ship the program in `myapp/node_programs/myapp_reader/` (with
   `iot_program.json`), register it, and add
   `<function model="iot.program" name="_iot_sync_builtin"/>` to a data
   file:

   ```python
   class IotProgram(models.Model):
       _inherit = 'iot.program'

       @api.model
       def _iot_builtin_programs(self):
           programs = super()._iot_builtin_programs()
           programs['myapp_reader'] = {'name': 'My App Reader', 'folder': 'myapp/node_programs/myapp_reader'}
           return programs
   ```

3. Check every request in the app's controllers:

   ```python
   from odoo.addons.iot_interfaces.controllers.main import authenticate

   @http.route('/myapp/node/v1/readings', type='http', auth='public', methods=['POST'],
               csrf=False, save_session=False)
   def readings(self):
       node, error = authenticate(roles=['myapp_reader'])
       if error:
           return error
       ...
   ```

4. In the program, call Odoo through the agent, which signs for you. The
   program holds no key:

   ```python
   urllib.request.urlopen(os.environ['IOT_PROXY_URL'] + '/myapp/node/v1/readings', data=...)
   ```

   The agent also provides `IOT_PROGRAM_DIR` (the program's files) and
   `IOT_DATA_DIR` (a folder kept across updates).

Tests can pair a Node and sign requests with
`odoo.addons.iot_interfaces.tests.common.pair`.

## API

| Route | |
| --- | --- |
| `GET /iot/install.sh`, `/iot/pi/iot_node_agent.py`, `/iot/pi/iot_auth.py` | Installer, agent and signing library (no key needed; they hold no secrets) |
| `POST /iot/v1/pair` | `{code, role, mac, macs, hostname}` → `{node, secret, name, role}` |
| `POST /iot/v1/hello` | Signed check-in. Sends `{version, program: {digest, error, setup_changed}}`; gets `{name, role, program: {version_id, digest, entrypoint, home, setup, files: [...]}, new_secret?}` |
| `GET /iot/v1/program/file/<id>` | Signed download of a program file for the Node's role |

Signed requests carry `X-IoT-Node`, `X-IoT-Timestamp` (milliseconds),
`X-IoT-MAC` and `X-IoT-Signature`. See `lib/iot_auth.py`.
