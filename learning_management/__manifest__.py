{
    'name': 'Learning Management System',
    'version': '19.0.1.1.0',
    'summary': 'Licences, Qualifications, Training & eLearning Management',
    'description': '''
        A comprehensive Learning Management System for tracking employee licences,
        qualifications, training and eLearning. Includes:
        - Library of licences, qualifications, training and eLearning
        - In-person training course scheduling and enrollment
        - SCORM-compatible eLearning delivery
        - Google Slides / PPT presentation delivery
        - Course Groups (packaged training catalogues)
        - Assignment of course groups to employees
        - Employee portal for training management
        - Manager approval for self-enrollment
    ''',
    'author': "Cliff's Country Crafts",
    'category': 'Human Resources/Learning',
    'depends': ['base', 'mail', 'hr', 'portal'],
    'data': [
        'security/access_levels.xml',
        'security/ir.model.access.csv',
        'data/access_roles.xml',
        'data/lms_data.xml',
        'views/lms_course_views.xml',
        'views/lms_course_session_views.xml',
        'views/lms_course_group_views.xml',
        'views/lms_employee_record_views.xml',
        'views/lms_assessment_views.xml',
        'views/lms_reports_views.xml',
        'views/lms_tna_report_template.xml',
        'views/lms_training_record_report.xml',
        'views/lms_hr_plan_views.xml',
        'views/lms_portal_templates.xml',
        'views/lms_menus.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'learning_management/static/src/css/lms_portal.css',
            'learning_management/static/src/js/lms_scorm.js',
        ],
        'web.assets_backend': [
            'learning_management/static/src/css/lms_backend.css',
            'learning_management/static/src/css/lms_tna_matrix.css',
            'learning_management/static/src/css/lms_expiring_report.css',
            'learning_management/static/src/css/lms_sessions_report.css',
            'learning_management/static/src/js/lms_portal_iframe.js',
            'learning_management/static/src/js/lms_tna_matrix.js',
            'learning_management/static/src/js/lms_expiring_report.js',
            'learning_management/static/src/js/lms_sessions_report.js',
            'learning_management/static/src/xml/lms_portal_iframe.xml',
            'learning_management/static/src/xml/lms_tna_matrix.xml',
            'learning_management/static/src/xml/lms_expiring_report.xml',
            'learning_management/static/src/xml/lms_sessions_report.xml',
        ],
    },
    'demo': [
        'demo/lms_demo_data.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
