{
    'name': 'AI Message Drafter',
    'version': '19.0.1.0.0',
    'category': 'Productivity/Discuss',
    'summary': 'Draft chatter messages and emails with AI from any record',
    'description': """
AI Message Drafter
==================
Adds an "AI Message" button to the chatter of every record, shown once a
Claude AI or Google Gemini API key is entered in Settings › General Settings
› Integrations (AI Integration Settings).

* The button opens a dialog where the user describes the message they want.
  "Fix with AI" asks Claude to write it (Google Gemini is the backup when
  Claude fails or has no key), using the record and its recent messages as
  context.
* The draft shows in a rich text editor: the user can edit it by hand or ask
  the AI for changes.
* "Copy to Chatter" puts the draft, with its formatting, into the chatter's
  message box, ready to send by email or log as a note. "Cancel" closes the
  dialog and leaves the chatter as it was.
* On Helpdesk tickets the AI also reads the ticket description, the customer
  sentiment notes and the recommended actions, and suggests a reply to the
  customer (the prompt is optional there).

A supporting app: it has no menu of its own and is only used from the chatter.
""",
    'author': "Cliff's Country Crafts",
    'depends': ['mail', 'html_editor', 'claude_ai_settings'],
    'assets': {
        'web.assets_backend': [
            'ai_message_drafter/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
