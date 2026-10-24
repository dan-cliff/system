{
    'name': 'Nextcloud Folders',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Create a Nextcloud folder for Odoo records and open it from the record',
    'description': """
Nextcloud Folders
=================
Creates a folder on your Nextcloud server (e.g. Nextcloud running on a
TrueNAS server on site) for the records you choose, and adds a "Folder"
button to those records' forms that opens it in Nextcloud.

* Settings > General Settings > Integrations > Nextcloud Folders: the
  server address, a service account and its app password, and the root
  folder every Odoo folder is created under. "Test Connection" checks them.
* Folder Rules (Settings > Nextcloud > Folder Rules): one per model, with
  the folder path built from the record's fields, e.g.
  ``Kennel Bookings/{partner_id}/{name}``. Each ``/`` starts a subfolder;
  characters a folder name can't hold (``/ \\ : * ? " < > |``) are replaced
  by ``-``, so dates (dd/mm/yyyy) become dd-mm-yyyy.
* Create Automatically: new records get their folder in the background as
  soon as they are saved (optionally only records matching a filter).
  "Create Folders for Existing Records" does the same for records already
  there. Otherwise the folder is created the first time someone presses
  the Folder button.
* The Folder button opens the folder's permanent Nextcloud link
  (``/f/<file id>``), which keeps working when the folder is renamed or
  moved in Nextcloud. Nextcloud asks people to sign in and only shows
  folders shared with them. Optionally a public (read-only) share link is
  created too.
* Records with a chatter get a note with the link when their folder is
  created. Folders are never renamed or deleted from Odoo.
* Folders (Settings > Nextcloud > Folders): every folder created, its
  record, path and link, and any error (failed folders are retried
  automatically, or with "Retry").
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['base_setup'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/ir_cron_data.xml',
        'views/nextcloud_folder_rule_views.xml',
        'views/nextcloud_folder_views.xml',
        'views/nextcloud_menus.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}
