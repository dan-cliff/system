from . import injury_rtw_case
from . import injury_case_note
from . import injury_medical_appointment
from . import injury_meeting
from . import injury_file_note
from . import injury_cost
from . import injury_rtw_plan
from . import injury_medical_certificate
from . import incident_report_ext
from . import injury_config_settings
from . import injury_case_report_wizard
# injury_case_document is a SQL view that references the Many2many relation
# tables of all the models above. It MUST be imported last so that those
# relation tables are created (via _auto_init) before this view's init() runs.
from . import injury_case_document
