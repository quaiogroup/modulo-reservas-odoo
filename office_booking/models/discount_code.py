# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OfficeDiscount(models.Model):
    _name = "office.discount"
    _description = "Código de descuento"
    _order = "name"

    name = fields.Char(string="Descripción", required=True)
    code = fields.Char(string="Código", required=True, copy=False)
    active = fields.Boolean(default=True)

    discount_type = fields.Selection([
        ("percent", "Porcentaje (%)"),
        ("fixed",   "Valor fijo"),
    ], string="Tipo de descuento", required=True, default="percent")

    discount_value = fields.Float(
        string="Valor",
        required=True,
        help="Porcentaje (0–100) o valor fijo según el tipo elegido.",
    )

    max_uses = fields.Integer(
        string="Usos máximos",
        default=0,
        help="0 = ilimitado.",
    )
    used_count = fields.Integer(
        string="Veces usado",
        default=0,
        readonly=True,
    )

    valid_from  = fields.Date(string="Válido desde")
    valid_until = fields.Date(string="Válido hasta")

    booking_ids = fields.One2many(
        "office.booking", "discount_code_id",
        string="Reservas con este código",
    )

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "Ya existe un código con ese valor."),
    ]

    def validate_for_booking(self, amount):
        """Verifica que el código sea usable. Retorna el monto de descuento o lanza ValidationError."""
        self.ensure_one()
        from odoo.fields import Date as FDate
        today = FDate.today()

        if not self.active:
            raise ValidationError(_("El código de descuento no está activo."))
        if self.valid_from and today < self.valid_from:
            raise ValidationError(_("El código aún no es válido."))
        if self.valid_until and today > self.valid_until:
            raise ValidationError(_("El código de descuento ha vencido."))
        if self.max_uses > 0 and self.used_count >= self.max_uses:
            raise ValidationError(_("Este código ha alcanzado el límite de usos."))

        if self.discount_type == "percent":
            return round(amount * min(self.discount_value, 100) / 100, 2)
        return min(self.discount_value, amount)

    def apply_use(self):
        self.ensure_one()
        self.sudo().write({"used_count": self.used_count + 1})

    def action_view_bookings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": f"Reservas con código {self.code}",
            "res_model": "office.booking",
            "view_mode": "list,form",
            "domain": [("discount_code_id", "=", self.id)],
        }
