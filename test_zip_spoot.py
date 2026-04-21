import sys, io
sys.path.insert(0, '/usr/lib/python3/dist-packages')

import odoo
from odoo.tools import config

config.parse_config([
    '--db_host=odoo-postgres',
    '--db_user=odoo',
    '--db_password=odoo',
    '--no-http',
])

registry = odoo.modules.registry.Registry.new('test_zip_spoot')

with registry.cursor() as cr:
    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})

    print("=== Importando ZIP spoot_test ===")
    with open('/tmp/spoot_test.zip', 'rb') as f:
        fp = io.BytesIO(f.read())

    try:
        result = env['ir.module.module']._import_zipfile(fp, force=False)
        cr.commit()
        print("RESULTADO:", result)
    except Exception as e:
        print("ERROR:", e)
        import traceback; traceback.print_exc()
        cr.rollback()
        sys.exit(1)

with registry.cursor() as cr2:
    env2 = odoo.api.Environment(cr2, odoo.SUPERUSER_ID, {})

    menus = env2['ir.ui.menu'].search([('name', 'like', 'Spoot Test')])
    print("\n=== Menús ===")
    for m in menus:
        print(" -", m.complete_name)

    views = env2['ir.ui.view'].search([('model', '=', 'spoot.test.item')])
    print(f"\n=== Vistas: {len(views)} ===")
    for v in views:
        print(" -", v.name)

    acls = env2['ir.model.access'].search([('name', 'like', 'spoot_test')])
    print(f"\n=== ACL: {len(acls)} ===")
    for a in acls:
        print(" -", a.name)

    mod = env2['ir.module.module'].search([('name', '=', 'spoot_test')])
    print(f"\n=== Estado módulo: {mod.state} ===")

    # Verificar que la tabla existe en la BD
    cr2.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'spoot_test_item')")
    tabla_existe = cr2.fetchone()[0]
    print(f"\n=== Tabla spoot_test_item en BD: {tabla_existe} ===")
