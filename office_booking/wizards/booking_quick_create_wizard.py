from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class OfficeBookingWizard(models.TransientModel):
    _name = "office.booking.wizard"
    _description = "Crear reserva rápida (admin)"

    office_id   = fields.Many2one("office.space", required=True)
    partner_id  = fields.Many2one("res.partner", string="Cliente", required=True)
    date        = fields.Date(required=True)

    office_pricing_mode = fields.Selection(
        related="office_id.pricing_mode",
        store=False,
        string="Modo de cobro",
    )

    # ── Modo jornadas ──────────────────────────────────────────────────────
    slot_type = fields.Selection([
        ("morning",   "Mañana (8:00 - 12:00)"),
        ("afternoon", "Tarde (14:00 - 18:00)"),
        ("full_day",  "Todo el día (8:00 - 18:00)"),
    ], required=False)

    # ── Modo por horas ─────────────────────────────────────────────────────
    hour_start = fields.Float(string="Hora inicio", digits=(4, 2))
    hour_end   = fields.Float(string="Hora fin",    digits=(4, 2))

    payment_mode = fields.Selection([
        ("bold", "Pasarela Bold"),
        ("plan", "Días del plan"),
    ], string="Método de pago", required=True, default="bold")

    subscription_id = fields.Many2one(
        "office.subscription",
        string="Plan del cliente",
        domain="[('partner_id', '=', partner_id), ('state', '=', 'active')]",
    )

    def action_create_booking(self):
        self.ensure_one()

        if self.payment_mode == "plan" and not self.subscription_id:
            raise ValidationError(_("Selecciona el plan activo del cliente."))

        mode = self.office_id.pricing_mode

        if mode == "hourly":
            if not self.hour_start and not self.hour_end:
                raise ValidationError(_("Indica la hora de inicio y fin de la reserva."))
            if self.hour_end <= self.hour_start:
                raise ValidationError(_("La hora de fin debe ser mayor que la hora de inicio."))
        else:
            if not self.slot_type:
                raise ValidationError(_("Selecciona la franja horaria."))

        vals = {
            "office_id":    self.office_id.id,
            "partner_id":   self.partner_id.id,
            "date":         self.date,
            "payment_mode": self.payment_mode,
            "state":        "confirmed" if self.payment_mode == "plan" else "pending_payment",
        }

        if mode == "hourly":
            vals["hour_start"] = self.hour_start
            vals["hour_end"]   = self.hour_end
        else:
            vals["slot_type"] = self.slot_type

        if self.payment_mode == "plan":
            if mode == "hourly":
                hours = max(self.hour_end - self.hour_start, 0.0)
                days = round(hours / 8.0, 2)
            else:
                days = 1.0 if self.slot_type == "full_day" else 0.5
            vals["subscription_id"]    = self.subscription_id.id
            vals["plan_days_consumed"] = days
            self.subscription_id.sudo().write({
                "remaining_days": self.subscription_id.remaining_days - days
            })

        booking = self.env["office.booking"].sudo().create(vals)

        return {
            "type":      "ir.actions.act_window",
            "res_model": "office.booking",
            "view_mode": "form",
            "res_id":    booking.id,
            "target":    "current",
        }
