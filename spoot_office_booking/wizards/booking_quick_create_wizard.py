from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class SpootBookingQuickCreateWizard(models.TransientModel):
    _name = "spoot.booking.quick.create.wizard"
    _description = "Crear reserva rápida (admin)"

    office_id   = fields.Many2one("spoot.office", required=True)
    partner_id  = fields.Many2one("res.partner", string="Cliente", required=True)
    date        = fields.Date(required=True)
    slot_type   = fields.Selection([
        ("morning",   "Mañana (8:00 - 12:00)"),
        ("afternoon", "Tarde (14:00 - 18:00)"),
        ("full_day",  "Todo el día (8:00 - 18:00)"),
    ], required=True)

    payment_mode = fields.Selection([
        ("bold", "Pasarela Bold"),
        ("plan", "Días del plan"),
    ], string="Método de pago", required=True, default="bold")

    subscription_id = fields.Many2one(
        "spoot.coworking.subscription",
        string="Plan del cliente",
        domain="[('partner_id', '=', partner_id), ('state', '=', 'active')]",
    )

    def action_create_booking(self):
        self.ensure_one()

        if self.payment_mode == "plan" and not self.subscription_id:
            raise ValidationError(_("Selecciona el plan activo del cliente."))

        vals = {
            "office_id":    self.office_id.id,
            "partner_id":   self.partner_id.id,
            "date":         self.date,
            "slot_type":    self.slot_type,
            "payment_mode": self.payment_mode,
            "state":        "confirmed" if self.payment_mode == "plan" else "pending_payment",
        }

        if self.payment_mode == "plan":
            days = 1.0 if self.slot_type == "full_day" else 0.5
            vals["subscription_id"]    = self.subscription_id.id
            vals["plan_days_consumed"] = days
            self.subscription_id.sudo().write({
                "remaining_days": self.subscription_id.remaining_days - days
            })

        booking = self.env["spoot.office.booking"].sudo().create(vals)

        return {
            "type":      "ir.actions.act_window",
            "res_model": "spoot.office.booking",
            "view_mode": "form",
            "res_id":    booking.id,
            "target":    "current",
        }
