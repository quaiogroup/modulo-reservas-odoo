import sys, io
sys.path.insert(0, '/usr/lib/python3/dist-packages')

import odoo
from odoo.tools import config

config.parse_config([
    '--db_host=odoo-postgres',
    '--db_user=odoo',
    '--db_password=odoo',
    '--addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons/spoot_office_booking',
    '--no-http',
])

registry = odoo.modules.registry.Registry.new('test_zip_db')

with registry.cursor() as cr:
    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})

    print("=== Importando ZIP ===")
    with open('/tmp/office_booking_test.zip', 'rb') as f:
        fp = io.BytesIO(f.read())

    try:
        result = env['ir.module.module']._import_zipfile(fp, force=False)
        cr.commit()
        print("RESULTADO:", result)
    except Exception as e:
        print("ERROR durante import:", e)
        import traceback; traceback.print_exc()
        cr.rollback()
        sys.exit(1)

# Cursor fresco para verificar (evita cache stale)
with registry.cursor() as cr2:
    env2 = odoo.api.Environment(cr2, odoo.SUPERUSER_ID, {})

    menus = env2['ir.ui.menu'].search([('name', 'like', 'Reservas')])
    print("\n=== Menús creados ===")
    for m in menus:
        print(" -", m.complete_name)

    views = env2['ir.ui.view'].search([('model', 'like', 'office.')])
    print(f"\n=== Vistas cargadas: {len(views)} ===")

    acls = env2['ir.model.access'].search([('name', 'like', 'access_office')])
    print(f"\n=== Reglas de acceso: {len(acls)} ===")
    for a in acls:
        print(" -", a.name)

    templates = env2['mail.template'].search([('model', 'like', 'office.')])
    print(f"\n=== Templates de mail: {len(templates)} ===")
    for t in templates:
        print(" -", t.name)

    crons = env2['ir.cron'].search([('name', 'like', 'Spoot')])
    print(f"\n=== Crons: {len(crons)} ===")
    for c in crons:
        print(" -", c.name)

    mod = env2['ir.module.module'].search([('name', '=', 'office_booking')])
    print(f"\n=== Estado del módulo: {mod.state} ===")
