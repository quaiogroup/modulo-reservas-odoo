from odoo import models, fields


class SpootCoworkingPlan(models.Model):
    _name = "spoot.coworking.plan"
    _description = "Planes de coworking"
    _order = "price asc"

    name = fields.Char(string="Nombre del plan", required=True)

    days_included = fields.Integer(
        string="Días incluidos",
        required=True
    )

    price = fields.Monetary(
        string="Precio",
        required=True
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        default=lambda self: self.env.company.currency_id.id,
        required=True
    )

    validity_days = fields.Integer(
        string="Duración (días)",
        help="Cantidad de días desde la activación hasta el vencimiento."
    )

    active = fields.Boolean(default=True)