from odoo import fields, models


class SpoottestItem(models.Model):
    _name = "spoot.test.item"
    _description = "Spoot Test Item"
    _order = "name"

    name = fields.Char(string="Nombre", required=True)
    notes = fields.Text(string="Notas")
