from odoo import models, fields

class SpootOfficeImage(models.Model):
    _name = "spoot.office.image"
    _description = "Imágenes de oficina"
    _order = "sequence, id"

    office_id = fields.Many2one("spoot.office", string="Oficina", required=True, ondelete="cascade")
    sequence = fields.Integer(string="Secuencia", default=10)
    name = fields.Char(string="Nombre")
    image_1920 = fields.Image(string="Imagen")
