# -*- coding: utf-8 -*-
{
    'name': 'Property',
    'version': '19.0.1.0.0',
    'category': 'Services/Property',
    'summary': 'Manage the premises the business owns or leases: details, ownership, leases, contracts, '
               'photos and floor plans',
    'description': """
        Property

        A catalogue of every premises the business holds, residential and
        commercial:

        - Ownership: Leased (externally owned, we are the tenant), Owned and
          Occupied, Owned and Leased Out, or Owned, Part Occupied and Part
          Leased Out. The form shows the landlord for leased premises, and the
          acquisition, valuation and disposal details for owned ones
        - Details: category (Residential, Commercial, …), property type,
          status, address, floor and land area, storeys, bedrooms, bathrooms,
          car spaces, year built, title reference, local authority and zoning
        - Leases: both ways (we are the tenant / we are the landlord), with the
          other party, premises, term, rent and payment frequency (annual rent
          worked out), bond, outgoings, incentives, rent reviews, options to
          renew, break clause and the signed lease document. Leases are
          activated, terminated and renewed (a renewal carries the lease on from
          the day after it expires), and expire by themselves
        - Contracts: insurance, cleaning, security, maintenance, utilities and
          other contracts for the property, with the supplier, term, cost and
          document
        - Reminders: a To Do activity for the Responsible before a lease
          expires, before options must be exercised, before a rent review and
          before a contract ends (lead time in Settings › Property)
        - Photo library: upload several photos at once; the first becomes the
          cover photo, and any photo can be made the cover
        - Floor plans: one or more per property (e.g. per level), as PDF or
          image, previewed on the plan
        - Categories, property types, statuses, payment frequencies, rent
          review types and contract types are option lists under Configuration

        Access: per-record-type permissions (Properties, Leases, Property
        Contracts) for Permission Management, see CLAUDE.md > Permissions.
        With Organisation Structure installed, properties, leases and contracts
        get the Division / Business Unit / Location / Department fields
        automatically; leases and contracts follow their property.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['base_setup', 'mail', 'hr', 'web_year_date'],
    'data': [
        'security/property_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/property_sequence_data.xml',
        'data/property_option_data.xml',
        'data/property_cron.xml',
        'views/property_property_views.xml',
        'views/property_lease_views.xml',
        'views/property_contract_views.xml',
        'views/property_photo_views.xml',
        'views/property_floor_plan_views.xml',
        'views/property_option_views.xml',
        'views/res_config_settings_views.xml',
        'views/property_menus.xml',
    ],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}
