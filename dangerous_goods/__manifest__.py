# -*- coding: utf-8 -*-
{
    'name': 'Dangerous Goods & Hazardous Substances',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Health & Safety',
    'summary': 'Chemical and Asbestos Registers with GHS classification and Australian WHS compliance',
    'description': """
        Dangerous Goods & Hazardous Substances Management for Australian workplaces.

        Chemical Register:
        - Full GHS (Globally Harmonised System) Rev 8 classification
        - Hazard classes, pictograms, H-codes and P-codes
        - Australian WHS Regulation compliance fields (scheduled substances, manifest quantities)
        - ADG transport class and AS 3833 storage class
        - SDS tracking with overdue alerts
        - PPE, engineering controls, first aid and emergency procedures
        - PDF chemical register report

        Asbestos Register:
        - Compliant with WHS Regulations 2017 Part 8.3 (Regs 425-429)
        - Friable and non-friable ACM tracking
        - Condition assessment and risk rating
        - Inspection history with photo attachments
        - Removal tracking with licensed contractor details
        - PDF asbestos register report

        Configuration:
        - All lookup/select data editable via Settings menu
        - Pre-seeded GHS hazard classes, pictograms, H-codes and P-codes
        - Pre-seeded ADG classes, DG storage classes, PPE types, asbestos forms and control measures
    """,
    'author': 'Custom',
    'depends': ['base', 'mail', 'hr'],
    'data': [
        'security/dangerous_goods_security.xml',
        'security/ir.model.access.csv',
        'data/dg_sequence_data.xml',
        'data/ghs_pictogram_data.xml',
        'data/ghs_hazard_class_data.xml',
        'data/ghs_hazard_statement_data.xml',
        'data/ghs_precautionary_statement_data.xml',
        'data/dg_config_data.xml',
        'data/dg_cron_data.xml',
        'views/ghs_views.xml',
        'views/dg_config_views.xml',
        'views/chemical_register_views.xml',
        'views/asbestos_register_views.xml',
        'report/chemical_register_report.xml',
        'report/asbestos_register_report.xml',
        'views/dangerous_goods_menus.xml',
    ],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}
