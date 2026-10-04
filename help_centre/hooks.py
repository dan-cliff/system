"""
Help Centre post-install hooks.

post_init_hook:
  1. Seeds demo articles (categories, tags, articles) if none exist.
  2. Seeds Help Centre roles into permission_management (if installed).
"""
import logging

_logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Demo data — categories, tags, articles
# ─────────────────────────────────────────────────────────────────────────────

_DEMO_CATEGORIES = [
    {
        'name': 'Getting Started',
        'icon': 'fa-rocket',
        'description': "New to Cliff's Country Crafts? Start here for orientation guides.",
        'sequence': 1,
        'color': 6,
    },
    {
        'name': '3D Print Farm',
        'icon': 'fa-print',
        'description': 'Managing print jobs, printers, filament spools, and Bambu Lab integrations.',
        'sequence': 2,
        'color': 1,
    },
    {
        'name': 'Warehouse & Reports',
        'icon': 'fa-archive',
        'description': 'Stock movement reports, inventory valuation, and warehouse management.',
        'sequence': 3,
        'color': 3,
    },
    {
        'name': 'Health & Safety',
        'icon': 'fa-medkit',
        'description': 'Incident reporting, ICAM investigations, injury management, and RTW plans.',
        'sequence': 4,
        'color': 9,
    },
    {
        'name': 'Point of Sale',
        'icon': 'fa-shopping-cart',
        'description': 'POS configuration, bag charges, and customer-facing settings.',
        'sequence': 5,
        'color': 4,
    },
    {
        'name': 'REST API',
        'icon': 'fa-plug',
        'description': 'Developer documentation for the Zyra REST API — authentication, endpoints, and examples.',
        'sequence': 6,
        'color': 2,
    },
    {
        'name': 'System Administration',
        'icon': 'fa-cog',
        'description': 'Advanced tools for administrators: custom SQL, storage monitoring, and user impersonation.',
        'sequence': 7,
        'color': 11,
    },
]

_DEMO_TAGS = [
    'Getting Started', 'How-to', 'Configuration', 'Reporting',
    'Safety', 'API', 'Administration', 'Print Farm', 'POS',
]

_DEMO_ARTICLES = [
    # ── Getting Started ──────────────────────────────────────────────────────
    {
        'name': "Welcome to the Help Centre",
        'slug': 'welcome-to-the-help-centre',
        'category': 'Getting Started',
        'audience': 'both',
        'is_featured': True,
        'sequence': 1,
        'tags': ['Getting Started'],
        'summary': "An overview of the Help Centre — what it is, how to navigate it, and how to use the AI chat assistant.",
        'content': """
<h2>What is the Help Centre?</h2>
<p>The Help Centre is your single source of truth for using Cliff's Country Crafts' Odoo system. It contains step-by-step guides, how-to articles, and configuration references for every custom module.</p>

<h2>How to access it</h2>
<p>There are two ways to open the Help Centre:</p>
<ul>
  <li><strong>From the backend:</strong> Click the <strong>Help</strong> button (question mark icon) in the top-right navigation bar. A slide-out panel will appear with search, featured articles, and the AI chat assistant.</li>
  <li><strong>From the website:</strong> Visit <a href="/help">/help</a> to browse the full public Help Centre. The floating <strong>Help</strong> bubble also appears on all website pages.</li>
</ul>

<h2>Navigating the panel</h2>
<p>The Help panel has two main tabs:</p>
<ul>
  <li><strong>Home:</strong> Search articles by keyword, or browse featured and recently updated articles.</li>
  <li><strong>Ask AI:</strong> Chat with the AI assistant for step-by-step guidance on any Odoo task.</li>
</ul>
<p>Click any article title to read it inside the panel. Use the <strong>← Back</strong> button to return to your previous view, or click <strong>Open full page ↗</strong> to read the article in a dedicated page.</p>

<div class="alert alert-info">
  <strong>Tip:</strong> Articles marked with a 🔒 lock icon are internal — they are only visible to authenticated Odoo users, not to the public website.
</div>
""",
    },
    {
        'name': "Using the AI Chat Assistant",
        'slug': 'using-the-ai-chat-assistant',
        'category': 'Getting Started',
        'audience': 'both',
        'is_featured': True,
        'sequence': 2,
        'tags': ['Getting Started', 'How-to'],
        'summary': "Learn how to get the most out of the AI chat assistant — what to ask and how to interpret its responses.",
        'content': """
<h2>What can the AI assistant do?</h2>
<p>The AI assistant can help you:</p>
<ul>
  <li>Find the right article for your question</li>
  <li>Walk you through step-by-step workflows</li>
  <li>Explain Odoo concepts in plain language</li>
  <li>Troubleshoot common issues</li>
</ul>

<h2>How to ask good questions</h2>
<p>The more specific your question, the better the answer. Examples of effective questions:</p>
<ul>
  <li><em>"How do I create a print job and assign it to a specific printer?"</em></li>
  <li><em>"What steps do I follow to report a workplace incident?"</em></li>
  <li><em>"How do I export a stock movement report to Excel?"</em></li>
</ul>

<h2>Article suggestions</h2>
<p>When the AI finds relevant articles, it shows them as chips below its response. Click any chip to read that article inside the panel without losing your chat history.</p>

<h2>Session persistence</h2>
<p>Your chat session is saved in your browser. If you close and reopen the panel, your conversation history will still be there. To start fresh, clear your browser's local storage or open a new incognito window.</p>

<div class="alert alert-warning">
  <strong>Note:</strong> AI responses are generated from the Help Centre article library and a language model. Always verify important steps in Odoo before acting on them.
</div>
""",
    },

    # ── 3D Print Farm ─────────────────────────────────────────────────────────
    {
        'name': "Creating Your First Print Job",
        'slug': 'creating-your-first-print-job',
        'category': '3D Print Farm',
        'audience': 'internal',
        'is_featured': False,
        'sequence': 1,
        'tags': ['Print Farm', 'How-to'],
        'summary': "Step-by-step guide to creating a print job, attaching a .3mf file, specifying required filaments, and sending it to a printer.",
        'content': """
<h2>Before you start</h2>
<p>Make sure you have:</p>
<ul>
  <li>A <strong>.3mf</strong> or <strong>.gcode</strong> file ready to upload</li>
  <li>At least one printer registered in the system</li>
  <li>The required filament spools added to inventory</li>
</ul>

<h2>Step 1 — Open the Print Farm app</h2>
<p>From the main menu, go to <strong>Print Farm</strong> → <strong>Jobs</strong> → click <strong>New</strong>.</p>

<h2>Step 2 — Fill in job details</h2>
<ol>
  <li>Enter a descriptive <strong>Job Name</strong> (e.g. "Customer Order #SO-00234 — Bracket").</li>
  <li>Set the <strong>Priority</strong> if this is urgent.</li>
  <li>In the <strong>Required Filaments</strong> tab, add each filament type and colour the job requires.</li>
</ol>

<h2>Step 3 — Attach the print file</h2>
<p>Click the <strong>📎 Attach</strong> button (or drag-and-drop) to upload the .3mf or .gcode file. The system stores the file against the job record.</p>

<h2>Step 4 — Queue the job</h2>
<p>Click <strong>Queue</strong>. The job moves to <em>Queued</em> state and becomes visible in the queue.</p>

<h2>Step 5 — Assign a printer</h2>
<p>Click <strong>Assign Printer</strong>. The system lists compatible printers based on the required filaments. Select a printer and click <strong>Assign &amp; Start</strong>. The job status changes to <em>Printing</em>.</p>

<div class="alert alert-info">
  <strong>Tip:</strong> If no compatible printer is shown, check that the printer's AMS slots are mapped to spools of the correct filament type and colour.
</div>
""",
    },
    {
        'name': "Managing Your Printer Fleet",
        'slug': 'managing-your-printer-fleet',
        'category': '3D Print Farm',
        'audience': 'internal',
        'is_featured': False,
        'sequence': 2,
        'tags': ['Print Farm', 'Configuration'],
        'summary': "How to add, edit, and configure Bambu Lab printers including IP address, access credentials, and AMS slot mapping.",
        'content': """
<h2>Adding a new printer</h2>
<ol>
  <li>Go to <strong>Print Farm</strong> → <strong>Configuration</strong> → <strong>Printers</strong>.</li>
  <li>Click <strong>New</strong>.</li>
  <li>Enter the printer's <strong>Name</strong>, <strong>IP Address</strong>, <strong>Serial Number</strong>, and <strong>Access Code</strong>.</li>
  <li>Select the <strong>Printer Model</strong> (e.g. Bambu Lab X1C).</li>
  <li>Save the record.</li>
</ol>

<h2>Connecting to Bambu Cloud</h2>
<p>Click <strong>Authenticate with Bambu Cloud</strong> to open the authentication wizard. Enter your Bambu account email and password. The system will retrieve the device list and populate the serial number and credentials automatically.</p>

<h2>Configuring AMS slots</h2>
<p>In the <strong>AMS Slots</strong> tab:</p>
<ol>
  <li>Add a row for each AMS unit and slot.</li>
  <li>Set the <strong>Unit</strong> (AMS 1, AMS 2, etc.) and <strong>Slot</strong> number (1–4).</li>
  <li>Select the <strong>Filament Spool</strong> currently loaded in that slot.</li>
</ol>
<p>The printer's compatibility for job assignment is calculated from these slot-to-spool mappings.</p>

<h2>Checking printer status</h2>
<p>The <strong>Status</strong> field refreshes automatically every 5 minutes via the background MQTT connection. You can force a refresh by clicking <strong>Refresh Status</strong> on the printer form.</p>

<div class="alert alert-warning">
  <strong>Important:</strong> The printer must be on the same local network as the Odoo server for local MQTT to work, or Bambu Cloud relay must be enabled.
</div>
""",
    },
    {
        'name': "Tracking Filament Spools",
        'slug': 'tracking-filament-spools',
        'category': '3D Print Farm',
        'audience': 'internal',
        'is_featured': False,
        'sequence': 3,
        'tags': ['Print Farm', 'How-to'],
        'summary': "How to add filament types, register individual spools, record weight usage, and manage spool lifecycle states.",
        'content': """
<h2>Filament types vs. spools</h2>
<p>The system separates <em>filament types</em> (e.g. Bambu PLA Basic — White) from <em>individual spools</em> (physical rolls with a remaining weight). This allows you to track how much of each colour you have available.</p>

<h2>Adding a filament type</h2>
<ol>
  <li>Go to <strong>Print Farm</strong> → <strong>Configuration</strong> → <strong>Filaments</strong>.</li>
  <li>Click <strong>New</strong> and fill in <strong>Material</strong>, <strong>Brand</strong>, and <strong>Colour</strong>.</li>
  <li>Save. The display name will appear as <em>[PLA] Bambu Basic (White)</em>.</li>
</ol>

<h2>Registering a new spool</h2>
<ol>
  <li>Go to <strong>Print Farm</strong> → <strong>Filament Spools</strong>.</li>
  <li>Click <strong>New</strong>.</li>
  <li>Select the <strong>Filament Type</strong>, enter the <strong>Initial Weight (g)</strong> (e.g. 1000 for a standard 1 kg spool), and set the state to <em>New</em>.</li>
  <li>Save. Once loaded into a printer, change the state to <em>In Use</em>.</li>
</ol>

<h2>Updating remaining weight</h2>
<p>After a print job completes, weigh the spool and update the <strong>Remaining Weight (g)</strong> field. When the spool reaches approximately 50 g, mark it as <em>Low</em> to trigger restocking alerts.</p>

<h2>Spool lifecycle</h2>
<p>States: <strong>New</strong> → <strong>In Use</strong> → <strong>Empty</strong> or <strong>Discarded</strong>. Empty spools are retained for record-keeping but are excluded from printer slot suggestions.</p>
""",
    },

    # ── Warehouse & Reports ───────────────────────────────────────────────────
    {
        'name': "Generating a Stock Movement Report",
        'slug': 'generating-a-stock-movement-report',
        'category': 'Warehouse & Reports',
        'audience': 'internal',
        'is_featured': False,
        'sequence': 1,
        'tags': ['Reporting', 'How-to'],
        'summary': "How to generate a PDF or Excel report of stock movements for a given date range, product, or warehouse location.",
        'content': """
<h2>Opening the Warehouse Reports app</h2>
<p>Go to <strong>Warehouse Reports</strong> from the main app menu. You will see the report dashboard with available report types.</p>

<h2>Stock Movement Report</h2>
<ol>
  <li>Click <strong>Stock Movements</strong>.</li>
  <li>Set the <strong>Date From</strong> and <strong>Date To</strong> fields to your desired date range.</li>
  <li>Optionally filter by <strong>Product</strong>, <strong>Location</strong>, or <strong>Operation Type</strong>.</li>
  <li>Click <strong>Generate PDF</strong> to preview and print, or <strong>Export to Excel</strong> to download a spreadsheet.</li>
</ol>

<h2>Reading the report</h2>
<p>Each row shows the product, quantity moved, source location → destination location, the responsible user, and the reference document (e.g. PO or SO number). The <strong>Ending Balance</strong> column shows the stock level at the end of the period.</p>

<div class="alert alert-info">
  <strong>Tip:</strong> For high-volume periods, narrow the date range or filter by product to keep the report manageable.
</div>
""",
    },
    {
        'name': "Running an Inventory Valuation Report",
        'slug': 'running-an-inventory-valuation-report',
        'category': 'Warehouse & Reports',
        'audience': 'internal',
        'is_featured': False,
        'sequence': 2,
        'tags': ['Reporting', 'How-to'],
        'summary': "How to generate an inventory valuation snapshot showing on-hand quantities and their monetary value.",
        'content': """
<h2>What the Valuation Report shows</h2>
<p>The Inventory Valuation Report shows the current (or historical) on-hand quantity and monetary value of each product, grouped by product category. It is useful for end-of-month stock takes and accounting reconciliation.</p>

<h2>Generating the report</h2>
<ol>
  <li>Go to <strong>Warehouse Reports</strong> → <strong>Inventory Valuation</strong>.</li>
  <li>Set the <strong>As of Date</strong> to get a historical snapshot, or leave blank for current stock.</li>
  <li>Optionally filter by <strong>Product Category</strong> or <strong>Location</strong>.</li>
  <li>Click <strong>Generate PDF</strong> or <strong>Export to Excel</strong>.</li>
</ol>

<h2>Understanding costing methods</h2>
<p>The value shown depends on the product's costing method:</p>
<ul>
  <li><strong>Standard Price:</strong> Uses the fixed cost on the product form.</li>
  <li><strong>Average Cost (AVCO):</strong> Uses the running weighted average cost.</li>
  <li><strong>First In First Out (FIFO):</strong> Uses the oldest purchase cost still in stock.</li>
</ul>
""",
    },

    # ── Health & Safety ───────────────────────────────────────────────────────
    {
        'name': "Reporting a Workplace Incident",
        'slug': 'reporting-a-workplace-incident',
        'category': 'Health & Safety',
        'audience': 'internal',
        'is_featured': False,
        'sequence': 1,
        'tags': ['Safety', 'How-to'],
        'summary': "Step-by-step guide to logging a workplace incident, completing the initial report, and initiating an ICAM investigation.",
        'content': """
<h2>Before you start</h2>
<p>An incident report should be submitted <strong>as soon as possible</strong> after the event — ideally within 24 hours. Gather the following before starting:</p>
<ul>
  <li>Date, time, and exact location of the incident</li>
  <li>Names of people involved and any witnesses</li>
  <li>A description of what happened</li>
  <li>Any immediate first aid or actions taken</li>
</ul>

<h2>Creating the incident record</h2>
<ol>
  <li>Go to <strong>Incident Management</strong> → <strong>Incidents</strong> → <strong>New</strong>.</li>
  <li>Set the <strong>Incident Date &amp; Time</strong>.</li>
  <li>Select the <strong>Location</strong> from the dropdown.</li>
  <li>Select the <strong>Incident Type</strong> (e.g. Near Miss, Injury, Property Damage).</li>
  <li>Select the <strong>Severity</strong>.</li>
  <li>In the <strong>Description</strong> tab, write a detailed narrative of what occurred.</li>
  <li>Add <strong>People Involved</strong> and <strong>Witnesses</strong> in the respective tabs.</li>
  <li>Click <strong>Submit Report</strong>.</li>
</ol>

<h2>Initiating an ICAM investigation</h2>
<p>For incidents with Severity ≥ <em>Medium</em>, click <strong>Start Investigation</strong>. This opens the ICAM investigation workflow where you can document causal factors, contributing factors, and corrective actions.</p>

<div class="alert alert-warning">
  <strong>Reminder:</strong> Serious incidents (fatality, hospitalisation, dangerous occurrence) may require notification to WorkSafe within 1 hour. Contact your H&amp;S Manager immediately.
</div>
""",
    },
    {
        'name': "Managing a Return-to-Work Plan",
        'slug': 'managing-a-return-to-work-plan',
        'category': 'Health & Safety',
        'audience': 'internal',
        'is_featured': False,
        'sequence': 2,
        'tags': ['Safety', 'How-to'],
        'summary': "How to create an RTW (Return-to-Work) plan, add medical appointments, track costs, and manage plan stages.",
        'content': """
<h2>What is an RTW Plan?</h2>
<p>A Return-to-Work plan is created when an employee sustains a workplace injury that requires time off or modified duties. It documents the rehabilitation pathway, medical appointments, agreed duties, and progress.</p>

<h2>Creating a new RTW Case</h2>
<ol>
  <li>Go to <strong>Injury Management</strong> → <strong>RTW Cases</strong> → <strong>New</strong>.</li>
  <li>Select the <strong>Injured Worker</strong>.</li>
  <li>Link the related <strong>Incident</strong> (if one was reported).</li>
  <li>Set the <strong>Injury Date</strong> and <strong>Nature of Injury</strong>.</li>
  <li>Click <strong>Save</strong>. The case starts in <em>Open</em> state.</li>
</ol>

<h2>Adding medical appointments</h2>
<p>In the <strong>Appointments</strong> tab, click <strong>Add a Line</strong> for each appointment:</p>
<ul>
  <li>Set the <strong>Date</strong>, <strong>Provider</strong> (doctor/physio), and <strong>Type</strong>.</li>
  <li>After the appointment, add the <strong>Outcome</strong> notes and any <strong>Certificates</strong> received.</li>
</ul>

<h2>Recording modified duties</h2>
<p>In the <strong>RTW Plan</strong> tab, document the agreed modified duties with start and review dates. Update the <strong>Hours Per Day</strong> and any restrictions as the employee progresses.</p>

<h2>Closing the case</h2>
<p>When the employee returns to full duties, click <strong>Close Case</strong>. Enter the <strong>Return-to-Full-Duties Date</strong> and any final notes. The case moves to <em>Closed</em> state and is archived.</p>
""",
    },

    # ── Point of Sale ─────────────────────────────────────────────────────────
    {
        'name': "Configuring POS Bag Charges",
        'slug': 'configuring-pos-bag-charges',
        'category': 'Point of Sale',
        'audience': 'internal',
        'is_featured': False,
        'sequence': 1,
        'tags': ['POS', 'Configuration'],
        'summary': "How to enable automatic bag charge line items in Point of Sale transactions.",
        'content': """
<h2>What the POS Bag Charges module does</h2>
<p>The <strong>POS Bag Charges</strong> module automatically adds a bag charge line item to POS orders when the cashier confirms that a bag was provided. This keeps bag charge revenue separate and reportable.</p>

<h2>Configuring the bag charge product</h2>
<ol>
  <li>Go to <strong>Point of Sale</strong> → <strong>Configuration</strong> → <strong>Settings</strong>.</li>
  <li>Scroll to the <strong>Bag Charges</strong> section.</li>
  <li>Select (or create) the <strong>Bag Charge Product</strong>. This should be a service product with the correct tax configuration.</li>
  <li>Set the <strong>Bag Charge Price</strong> (e.g. $0.15 per bag).</li>
  <li>Save the settings.</li>
</ol>

<h2>Using bag charges during a sale</h2>
<ol>
  <li>At the POS terminal, complete the order as normal.</li>
  <li>Before payment, tap <strong>Add Bag Charge</strong>. A prompt asks for the number of bags.</li>
  <li>Enter the quantity. The bag charge line is added to the order at the configured price.</li>
  <li>Proceed to payment as normal.</li>
</ol>

<div class="alert alert-info">
  <strong>Tip:</strong> Bag charge revenue is tracked separately in sales reports under the Bag Charge product category, making it easy to report on for compliance purposes.
</div>
""",
    },

    # ── REST API ─────────────────────────────────────────────────────────────
    {
        'name': "API Authentication and Keys",
        'slug': 'api-authentication-and-keys',
        'category': 'REST API',
        'audience': 'external',
        'is_featured': False,
        'sequence': 1,
        'tags': ['API', 'Configuration'],
        'summary': "How to create API keys, authenticate requests, and understand the supported authentication methods.",
        'content': """
<h2>Supported authentication methods</h2>
<p>The Zyra REST API supports three ways to pass your API key:</p>
<table>
  <thead>
    <tr><th>Method</th><th>Example</th></tr>
  </thead>
  <tbody>
    <tr><td>Header: <code>X-API-Key</code></td><td><code>X-API-Key: your_key_here</code></td></tr>
    <tr><td>Header: <code>Authorization</code></td><td><code>Authorization: Bearer your_key_here</code></td></tr>
    <tr><td>Query parameter</td><td><code>/api/model/res.partner?api_key=your_key_here</code></td></tr>
  </tbody>
</table>

<h2>Creating an API key</h2>
<ol>
  <li>Log in to Odoo as an administrator.</li>
  <li>Go to <strong>REST API</strong> → <strong>API Keys</strong> → <strong>New</strong>.</li>
  <li>Enter a descriptive <strong>Name</strong> (e.g. "Mobile App Key").</li>
  <li>Set an optional <strong>Expiry Date</strong>.</li>
  <li>Click <strong>Generate Key</strong>. Copy and store the key securely — it is only shown once.</li>
</ol>

<h2>Rate limits</h2>
<p>Each API key is subject to a per-minute request limit configured in <strong>REST API</strong> → <strong>Settings</strong>. Exceeding the limit returns a <code>429 Too Many Requests</code> response. Implement exponential back-off in your client.</p>

<div class="alert alert-warning">
  <strong>Security:</strong> Treat your API key like a password. Never expose it in client-side JavaScript or commit it to source control. Regenerate it immediately if compromised.
</div>
""",
    },
    {
        'name': "Querying Model Data via the API",
        'slug': 'querying-model-data-via-the-api',
        'category': 'REST API',
        'audience': 'external',
        'is_featured': False,
        'sequence': 2,
        'tags': ['API', 'How-to'],
        'summary': "How to use the /api/model/ endpoint to retrieve, filter, and paginate Odoo model records.",
        'content': """
<h2>Basic request structure</h2>
<p>Model endpoints follow this pattern:</p>
<pre><code>GET /api/model/&lt;model_name&gt;</code></pre>
<p>For example, to list all contacts:</p>
<pre><code>GET /api/model/res.partner
X-API-Key: your_key_here</code></pre>

<h2>Filtering results</h2>
<p>Pass a JSON domain as the <code>domain</code> query parameter (URL-encoded):</p>
<pre><code>GET /api/model/res.partner?domain=[["is_company","=",true]]</code></pre>
<p>Domains follow the standard Odoo domain syntax: <code>[["field", "operator", "value"]]</code>.</p>

<h2>Selecting fields</h2>
<p>By default all stored fields are returned. To limit the response size, pass a <code>fields</code> parameter:</p>
<pre><code>GET /api/model/res.partner?fields=["name","email","phone"]</code></pre>

<h2>Pagination</h2>
<p>Use <code>limit</code> and <code>offset</code> to paginate large result sets:</p>
<pre><code>GET /api/model/res.partner?limit=50&amp;offset=100</code></pre>

<h2>Single record</h2>
<p>To retrieve a specific record by ID:</p>
<pre><code>GET /api/model/res.partner/42</code></pre>

<div class="alert alert-info">
  <strong>Note:</strong> The available models and fields are controlled by the Model Endpoint configuration in <strong>REST API</strong> → <strong>Model Endpoints</strong>. Contact your administrator to enable access to additional models.
</div>
""",
    },

    # ── System Administration ─────────────────────────────────────────────────
    {
        'name': "Running Custom SQL Queries",
        'slug': 'running-custom-sql-queries',
        'category': 'System Administration',
        'audience': 'internal',
        'is_featured': False,
        'sequence': 1,
        'tags': ['Administration', 'How-to'],
        'summary': "How to use Query Deluxe to execute raw PostgreSQL queries, review results, and export to PDF.",
        'content': """
<h2>When to use Query Deluxe</h2>
<p>Query Deluxe is for administrators who need to run ad-hoc SQL queries — for example, to extract data for custom reports or to investigate data quality issues. It should be used with care as queries run directly on the live database.</p>

<h2>Running a query</h2>
<ol>
  <li>Go to <strong>Query Deluxe</strong> from the main menu.</li>
  <li>Enter your SQL in the query editor. Example:</li>
</ol>
<pre><code>SELECT id, name, email
FROM res_partner
WHERE is_company = true
ORDER BY name
LIMIT 100;</code></pre>
<ol start="3">
  <li>Click <strong>Run Query</strong>. Results appear in the table below.</li>
  <li>Click <strong>Export to PDF</strong> to generate a printable report.</li>
</ol>

<div class="alert alert-warning">
  <strong>Important — read-only:</strong> Only <code>SELECT</code> statements are permitted. Any attempt to run <code>INSERT</code>, <code>UPDATE</code>, <code>DELETE</code>, or DDL commands will be blocked.
</div>

<h2>Tips</h2>
<ul>
  <li>Use <code>LIMIT</code> on large tables to avoid timeouts.</li>
  <li>Odoo table names follow the pattern <code>model_name</code> with dots replaced by underscores (e.g. <code>res.partner</code> → <code>res_partner</code>).</li>
  <li>The <code>active</code> column filters out archived records — add <code>AND active = true</code> to exclude them.</li>
</ul>
""",
    },
    {
        'name': "Monitoring Database Storage",
        'slug': 'monitoring-database-storage',
        'category': 'System Administration',
        'audience': 'internal',
        'is_featured': False,
        'sequence': 2,
        'tags': ['Administration', 'How-to'],
        'summary': "How to use the Storage Dashboard to see which Odoo models are consuming the most database space.",
        'content': """
<h2>Opening the Storage Dashboard</h2>
<p>Go to <strong>Storage Dashboard</strong> from the main app menu. The dashboard loads and shows a table of all Odoo models ranked by disk usage.</p>

<h2>Reading the dashboard</h2>
<p>The dashboard shows:</p>
<ul>
  <li><strong>Model</strong> — the technical Odoo model name</li>
  <li><strong>Table Size</strong> — space used by the table data itself</li>
  <li><strong>Index Size</strong> — space used by database indexes</li>
  <li><strong>Total Size</strong> — combined table + index size</li>
  <li><strong>Row Count</strong> — approximate number of records</li>
</ul>

<h2>Common large models</h2>
<p>Models that tend to grow quickly:</p>
<ul>
  <li><code>mail.message</code> — every chatter message</li>
  <li><code>ir.attachment</code> — uploaded files and documents</li>
  <li><code>stock.move.line</code> — individual inventory movements</li>
  <li><code>account.move.line</code> — journal entry lines</li>
</ul>

<h2>Reducing storage usage</h2>
<p>If a model is unexpectedly large:</p>
<ol>
  <li>Archive old records in that model.</li>
  <li>Check whether a scheduled action or automation is creating duplicate records.</li>
  <li>Contact Odoo.sh support if the database size is approaching the plan limit.</li>
</ol>
""",
    },
    {
        'name': "Impersonating a User for Troubleshooting",
        'slug': 'impersonating-a-user-for-troubleshooting',
        'category': 'System Administration',
        'audience': 'internal',
        'is_featured': False,
        'sequence': 3,
        'tags': ['Administration', 'How-to'],
        'summary': "How to use the Login As Any User systray button to temporarily log in as another user to debug access or configuration issues.",
        'content': """
<h2>What is user impersonation?</h2>
<p>The <strong>Login As Any User</strong> feature lets an administrator temporarily switch to any other user's session without knowing their password. This is useful for diagnosing permission issues or reproducing bugs reported by a specific user.</p>

<div class="alert alert-warning">
  <strong>Use responsibly:</strong> While impersonating another user, all actions you take are recorded under <em>their</em> account. Only use this feature for legitimate troubleshooting — never for accessing confidential data without authorisation.
</div>

<h2>How to impersonate a user</h2>
<ol>
  <li>In the Odoo backend top bar, click the <strong>👤 Login As</strong> button (visible to administrators only).</li>
  <li>A dropdown appears with a search box. Start typing the user's name or email.</li>
  <li>Select the user. The page reloads and you are now logged in as that user.</li>
</ol>

<h2>Returning to your own account</h2>
<p>A banner at the top of the screen will remind you that you are impersonating another user. Click <strong>Return to My Account</strong> in the banner, or click the user menu in the top-right corner and select <strong>End Impersonation</strong>.</p>

<h2>What you can and cannot do</h2>
<ul>
  <li>✅ You see exactly what the user sees — their menus, their records, their access rights.</li>
  <li>✅ Useful for testing permission profiles and access control.</li>
  <li>❌ You cannot impersonate another administrator or a system superuser.</li>
  <li>❌ Impersonation sessions are logged in the audit trail.</li>
</ul>
""",
    },
]


def _seed_demo_articles(env):
    """
    Create demo articles for all custom modules.
    Skips entirely if any categories already exist (idempotent).
    """
    Category = env['help.category'].sudo()
    if Category.search_count([]) > 0:
        return

    _logger.info('help_centre: seeding demo articles…')

    # ── Create categories ──────────────────────────────────────────────────────
    cat_map = {}
    for cat_data in _DEMO_CATEGORIES:
        cat = Category.create(cat_data)
        cat_map[cat_data['name']] = cat

    # ── Create tags ────────────────────────────────────────────────────────────
    Tag = env['help.tag'].sudo()
    tag_map = {}
    for tag_name in _DEMO_TAGS:
        tag = Tag.create({'name': tag_name})
        tag_map[tag_name] = tag

    # ── Create articles ────────────────────────────────────────────────────────
    Article = env['help.article'].sudo()
    for art_data in _DEMO_ARTICLES:
        tag_ids = [(6, 0, [tag_map[t].id for t in art_data.get('tags', []) if t in tag_map])]
        Article.create({
            'name': art_data['name'],
            'slug': art_data['slug'],
            'summary': art_data.get('summary', ''),
            'content': art_data['content'].strip(),
            'audience': art_data['audience'],
            'state': 'published',
            'is_featured': art_data.get('is_featured', False),
            'sequence': art_data.get('sequence', 10),
            'category_id': cat_map.get(art_data['category'], env['help.category'].sudo().browse([])).id or False,
            'tag_ids': tag_ids,
            'author_id': env.ref('base.user_admin').id,
        })

    _logger.info('help_centre: created %d demo articles across %d categories.',
                 len(_DEMO_ARTICLES), len(_DEMO_CATEGORIES))


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def post_init_hook(env):
    """Seed demo articles + Help Centre roles into permission_management (if installed)."""

    # 1. Demo content
    try:
        _seed_demo_articles(env)
    except Exception as e:
        _logger.warning('help_centre: demo article seeding failed: %s', e)

    # 2. Permission management roles
    IrModule = env['ir.module.module']
    perm_mod = IrModule.search(
        [('name', '=', 'permission_management'), ('state', '=', 'installed')],
        limit=1,
    )
    if perm_mod:
        try:
            env['permission.role']._load_role_library()
            _logger.info('help_centre: Help Centre roles seeded into permission_management.')
        except Exception as e:
            _logger.warning('help_centre: Could not seed permission roles: %s', e)

    # 3. Populate module coverage table for all currently-installed modules.
    #    Articles will be generated by the nightly cron or manually via the
    #    Configuration → Module Coverage menu.
    try:
        created = env['help.module.coverage'].sync_installed_modules()
        _logger.info(
            'help_centre: %d module coverage record(s) created on install.', created
        )
    except Exception as e:
        _logger.warning('help_centre: module coverage sync failed: %s', e)

    # 4. Register the /help/contents page in website.page so it appears in
    #    Website → Pages.
    try:
        _register_contents_website_page(env)
    except Exception as e:
        _logger.warning('help_centre: could not register /help/contents website page: %s', e)


def _register_contents_website_page(env):
    """
    Create a website.page record for /help/contents so it appears in the
    Website backend under Pages.  Skipped if the record already exists.
    """
    WebsitePage = env['website.page'].sudo()
    existing = WebsitePage.search([('url', '=', '/help/contents')], limit=1)
    if existing:
        return

    # Find the QWeb view we created
    view = env['ir.ui.view'].sudo().search([
        ('key', '=', 'help_centre.website_help_contents'),
    ], limit=1)
    if not view:
        return

    WebsitePage.create({
        'view_id': view.id,
        'url': '/help/contents',
        'is_published': True,
        'website_indexed': True,
    })
    _logger.info('help_centre: /help/contents registered as a website page.')
