from odoo import models, fields


class OfficePlan(models.Model):
    _name = "office.plan"
    _description = "Planes de coworking"
    _order = "price asc"

    name = fields.Char(string="Nombre del plan", required=True)
    description = fields.Text(string="Descripción")


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