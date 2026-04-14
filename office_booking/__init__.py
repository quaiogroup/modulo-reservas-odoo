from . import models
from . import controllers
from . import wizards


def pre_init_hook(env):
    """Register ir.model records + external IDs before data files are loaded.
    Needed for ZIP upload where _reflect() hasn't run yet."""
    IrModel = env['ir.model']
    IrModelData = env['ir.model.data']

    models_info = [
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

    for model_name, display_name, xml_id in models_info:
        model_rec = IrModel.sudo().search([('model', '=', model_name)], limit=1)
        if not model_rec:
            model_rec = IrModel.sudo().create({
                'name': display_name,
                'model': model_name,
                'state': 'base',
            })
        existing = IrModelData.sudo().search([
            ('module', '=', 'office_booking'), ('name', '=', xml_id)
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
    """Create model access rules after installation (works for ZIP upload too)."""
    IrModel = env['ir.model']
    IrModelAccess = env['ir.model.access']
    group_user = env.ref('base.group_user')
    group_system = env.ref('base.group_system')

    rules = [
        # (model,                  name,                               group,       r, w, c, d)
        ('office.space',        'access_office_space_user',        group_user,   1,0,0,0),
        ('office.space',        'access_office_space_manager',     group_system, 1,1,1,1),
        ('office.booking',      'access_office_booking_user',      group_user,   1,1,1,0),
        ('office.booking',      'access_office_booking_manager',   group_system, 1,1,1,1),
        ('office.image',        'access_office_image_user',        group_user,   1,0,0,0),
        ('office.image',        'access_office_image_manager',     group_system, 1,1,1,1),
        ('office.booking.wizard','access_office_booking_wizard',   group_user,   1,1,1,1),
        ('office.service',      'access_office_service_user',      group_user,   1,0,0,0),
        ('office.service',      'access_office_service_manager',   group_system, 1,1,1,1),
        ('office.subscription', 'access_office_subscription_user', group_user,   1,0,0,0),
        ('office.subscription', 'access_office_subscription_manager', group_system, 1,1,1,1),
        ('office.plan',         'access_office_plan_user',         group_user,   1,0,0,0),
        ('office.plan',         'access_office_plan_manager',      group_system, 1,1,1,1),
        ('office.block',        'access_office_block_user',        group_user,   1,0,0,0),
        ('office.block',        'access_office_block_manager',     group_system, 1,1,1,1),
        ('office.availability', 'access_office_availability',      group_user,   1,0,0,0),
        ('office.settings',     'access_office_settings',          group_system, 1,1,1,1),
        ('office.discount',     'access_office_discount_user',     group_user,   1,0,0,0),
        ('office.discount',     'access_office_discount_manager',  group_system, 1,1,1,1),
    ]

    for model_name, name, group, r, w, c, d in rules:
        model = IrModel.search([('model', '=', model_name)], limit=1)
        if not model:
            continue
        if not IrModelAccess.search([('name', '=', name)], limit=1):
            IrModelAccess.create({
                'name': name,
                'model_id': model.id,
                'group_id': group.id,
                'perm_read': bool(r),
                'perm_write': bool(w),
                'perm_create': bool(c),
                'perm_unlink': bool(d),
            })

    # Security rules
    IrRule = env['ir.rule']
    booking_model = IrModel.search([('model', '=', 'office.booking')], limit=1)
    subscription_model = IrModel.search([('model', '=', 'office.subscription')], limit=1)

    if booking_model and not IrRule.search([('name', '=', 'Reservas: solo las propias (usuarios)')], limit=1):
        IrRule.create({
            'name': 'Reservas: solo las propias (usuarios)',
            'model_id': booking_model.id,
            'groups': [(4, group_user.id)],
            'domain_force': "[('partner_id', '=', user.partner_id.id)]",
            'perm_read': True,
            'perm_write': True,
            'perm_create': False,
            'perm_unlink': False,
        })

    if subscription_model and not IrRule.search([('name', '=', 'Suscripciones: solo las propias (usuarios)')], limit=1):
        IrRule.create({
            'name': 'Suscripciones: solo las propias (usuarios)',
            'model_id': subscription_model.id,
            'groups': [(4, group_user.id)],
            'domain_force': "[('partner_id', '=', user.partner_id.id)]",
            'perm_read': True,
            'perm_write': False,
            'perm_create': False,
            'perm_unlink': False,
        })

    # Bind report to model (optional field, set after model is guaranteed to exist)
    if booking_model:
        report = env['ir.actions.report'].search(
            [('report_name', '=', 'office_booking.report_booking_receipt_template')], limit=1
        )
        if report and not report.binding_model_id:
            report.binding_model_id = booking_model.id
