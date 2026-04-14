from . import models
from . import controllers
from . import wizards


def post_init_hook(env):
    """Load all data files after models are registered in the registry.
    Using post_init_hook ensures Python models are available for view
    validation and model_id resolution — works for both --init and ZIP upload."""
    import os
    from odoo.tools.convert import convert_file

    module_path = os.path.dirname(os.path.abspath(__file__))

    data_files = [
        # Security
        'security/ir_model_access.xml',
        'security/ir_rules.xml',
        # Reports
        'reports/booking_receipt.xml',
        # Data
        'data/mail_templates.xml',
        'data/ir_cron_data.xml',
        # Views
        'views/office_views.xml',
        'views/booking_views.xml',
        'views/office_block_views.xml',
        'views/coworking_plan_views.xml',
        'views/coworking_subscription_views.xml',
        'views/availability_views.xml',
        'views/discount_views.xml',
        'views/settings_views.xml',
        'views/client_views.xml',
        'views/portal_templates.xml',
        'views/website_templates.xml',
        # Menus last
        'views/menu_views.xml',
    ]

    for filename in data_files:
        convert_file(
            env, 'office_booking', filename, {}, 'init', False,
            pathname=os.path.join(module_path, *filename.split('/')),
        )
