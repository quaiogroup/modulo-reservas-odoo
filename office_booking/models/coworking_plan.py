from odoo import models, fields


class OfficePlan(models.Model):
    _name = "office.plan"
    _description = "Planes de coworking"
    _order = "price asc"
    _inherit = ["image.mixin"]   # añade image_1920, image_1024, etc.

    name = fields.Char(string="Nombre del plan", required=True)
    description = fields.Text(string="Descripción")
    image_1920 = fields.Image(string="Foto del plan")

    office_ids = fields.Many2many(
        "office.space",
        "office_plan_space_rel",
        "plan_id",
        "office_id",
        string="Oficinas incluidas",
        help="Si se especifican oficinas, este plan SOLO permite reservar esas oficinas. "
             "Si se deja vacío, el plan aplica a todas las oficinas.",
    )

    def covers_office(self, office):
        """Devuelve True si el plan permite reservar la oficina dada.
        Sin oficinas configuradas → aplica a todas."""
        self.ensure_one()
        if not self.office_ids:
            return True
        office_id = office.id if hasattr(office, "id") else int(office)
        return office_id in self.office_ids.ids


    days_included = fields.Integer(
        string="Días incluidos",
        required=True
    )

    price = fields.Monetary(
        string="Precio",
        required=True,
        currency_field="currency_id"
    )

    currency_id = fields.Many2one(
    "res.currency",
    string="Moneda",
    default=lambda self: self.env.company.currency_id,
    required=True
)

    validity_days = fields.Integer(
        string="Duración (días)",
        help="Cantidad de días desde la activación hasta el vencimiento."
    )


    active = fields.Boolean(default=True)