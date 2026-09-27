"""Animal notes used to be one text field on the animal; they are now dated
note records. Keep what was written as each animal's first note."""
from odoo import SUPERUSER_ID, api
from odoo.tools import html2plaintext


def migrate(cr, version):
    cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = 'zoo_animal' AND column_name = 'notes'")
    if not cr.fetchone():
        return
    cr.execute("""
        SELECT id, notes, write_date, write_uid FROM zoo_animal
         WHERE notes IS NOT NULL AND notes NOT IN ('', '<p><br></p>', '<p></p>')
    """)
    rows = cr.fetchall()
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['zoo.animal.note'].create([{
        'animal_id': animal_id,
        'date': write_date,
        'user_id': write_uid,
        'summary': 'Earlier notes',
        'note': notes,
    } for animal_id, notes, write_date, write_uid in rows if html2plaintext(notes or '').strip()])
    cr.execute('ALTER TABLE zoo_animal DROP COLUMN notes')
