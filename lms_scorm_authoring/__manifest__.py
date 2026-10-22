{
    'name': 'SCORM Authoring',
    'version': '19.0.1.1.0',
    'summary': 'Design, review, approve and publish SCORM eLearning courses for the LMS',
    'description': '''
        SCORM Authoring - a companion app to the Learning Management System.

        - Drag-and-drop slide editor: text, pictures, video, audio, shapes, buttons,
          hotspots, web embeds, tabs, accordions, flip cards, labelled graphics,
          questions (multiple choice, multiple response, true/false, fill in the blank,
          matching, sequence, survey) and a results summary
        - Import PowerPoint (.pptx) and Google Slides presentations: the file is
          checked, then every slide is converted into editable slide content
        - Slide gates: Continue only shows once the required items are done, the
          minimum time has passed and the slide's pass mark is reached; limited
          attempts can send learners back to a review slide
        - Assessments: scored questions, passing score, attempts, results slide;
          the score and pass/fail are reported to the LMS
        - Branding per course (or the company's) and configurable learner button labels
        - Versions: a new version stays a draft, invisible to learners, until it is
          approved and published
        - Approval workflow with named approvers, and review comments pinned to
          slides that learners never see
        - Preview mode to try a course without touching the LMS or training records
        - Download a SCORM 1.2 / 2004 .zip for other systems, or pick the published
          course in the LMS Course Library
        - Generate a course's slides with AI (Claude or Google Gemini, using the keys on
          Settings › General Settings › Integrations), with optional knowledge checks
          and a final exam
    ''',
    'author': "Cliff's Country Crafts",
    'category': 'Human Resources/Learning',
    'depends': ['learning_management', 'mail', 'web'],
    'external_dependencies': {'python': ['lxml', 'requests']},
    'data': [
        'security/lms_scorm_security.xml',
        'security/ir.model.access.csv',
        'data/lms_scorm_data.xml',
        'views/lms_scorm_course_views.xml',
        'views/lms_scorm_wizard_views.xml',
        'views/lms_course_views.xml',
        'views/lms_scorm_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'lms_scorm_authoring/static/src/ai_progress/*',
            'lms_scorm_authoring/static/src/editor/*',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
