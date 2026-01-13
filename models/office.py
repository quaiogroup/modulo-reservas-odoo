from odoo import models, fields

class SpootOffice(models.Model):
    _name = "spoot.office"
    _description = "Oficina reservable"
    _order = "name"
    _inherit = ["image.mixin"]   # 👈 esto agrega image_1920, image_1024, etc.

    name = fields.Char(string="Nombre de la oficina", required=True)
    image_1920 = fields.Image(string="Imagen principal")

    image_ids = fields.One2many(
        "spoot.office.image",
        "office_id",
        string="Galería"
    )
    description = fields.Text(string="Descripción")
    # QUITA: image = fields.Binary(...)
    location = fields.Char(string="Ubicación")
    capacity = fields.Integer(string="Capacidad")

    price_morning = fields.Monetary(string="Precio mañana")
    price_afternoon = fields.Monetary(string="Precio tarde")
    price_full_day = fields.Monetary(string="Precio día completo")

    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        default=lambda self: self.env.company.currency_id.id,
    )

    active = fields.Boolean(string="Activo", default=True)
    short_description = fields.Char(string="Descripción corta para web")
