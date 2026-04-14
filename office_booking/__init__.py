from . import models
from . import controllers
from . import wizards


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
