from . import models
from . import controllers
from . import wizards

import logging
_logger = logging.getLogger(__name__)

_MODELS = [
    ('office.booking',        'Office Booking',        'model_office_booking'),
    ('office.space',          'Office Space',          'model_office_space'),
    ('office.plan',           'Office Plan',           'model_office_plan'),
    ('office.subscription',   'Office Subscription',   'model_office_subscription'),
    ('office.service',        'Office Service',        'model_office_service'),
    ('office.block',          'Office Block',          'model_office_block'),
    ('office.image',          'Office Image',          'model_office_image'),
    ('office.availability',   'Office Availability',   'model_office_availability'),
    ('office.settings',       'Office Settings',       'model_office_settings'),
    ('office.discount',       'Office Discount',       'model_office_discount'),
    ('office.booking.wizard', 'Office Booking Wizard', 'model_office_booking_wizard'),
]

_DATA_FILES = [
    'security/ir_model_access.xml',
    'security/ir_rules.xml',
    'reports/booking_receipt.xml',
    'data/mail_templates.xml',
    'data/ir_cron_data.xml',
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
    'views/menu_views.xml',
]


def _reflect_models(env):
    """Ensure all module models have ir.model records and external IDs."""
    # 1. Trigger full reflection via registry
    try:
        env.registry.setup_models(env.cr)
        env.invalidate_all()
    except Exception as e:
        _logger.warning("office_booking: setup_models warning: %s", e)

    # 2. Ensure each model has an ir.model record + ir.model.data external ID
    IrModel = env['ir.model']
    IrModelData = env['ir.model.data']
    for model_name, display_name, xml_id in _MODELS:
        model_rec = IrModel.sudo().search([('model', '=', model_name)], limit=1)
        if not model_rec:
            _logger.warning("office_booking: model %s not found, creating minimal record", model_name)
            model_rec = IrModel.sudo().create({
                'name': display_name,
                'model': model_name,
                'state': 'base',
            })
        existing = IrModelData.sudo().search([
            ('module', '=', 'office_booking'), ('name', '=', xml_id),
        ], limit=1)
        if not existing:
            IrModelData.sudo().create({
                'module': 'office_booking',
                'name': xml_id,
                'model': 'ir.model',
                'res_id': model_rec.id,
                'noupdate': False,
            })


def post_init_hook(env):
    """Load all views, menus, and data after models are registered."""
    import os
    from odoo.tools.convert import convert_file

    # Ensure ir.model records + external IDs exist before loading XML
    _reflect_models(env)

    module_path = os.path.dirname(os.path.abspath(__file__))

    for filename in _DATA_FILES:
        filepath = os.path.join(module_path, *filename.split('/'))
        try:
            convert_file(env, 'office_booking', filename, {}, 'init', False, pathname=filepath)
            _logger.info("office_booking: loaded %s", filename)
        except Exception as e:
            _logger.error("office_booking: FAILED loading %s: %s", filename, e)
