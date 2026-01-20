from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class SpootBookingQuickCreateWizard(models.TransientModel):
    _name = "spoot.booking.quick.create.wizard"
    _description = "Crear reserva rápida (admin)"

    office_id = fields.Many2one("spoot.office", required=True)
    partner_id = fields.Many2one("res.partner", string="Cliente", required=True)
    date = fields.Date(required=True)
    slot_type = fields.Selection([
        ("morning", "Mañana (8:00 - 12:00)"),
        ("afternoon", "Tarde (14:00 - 18:00)"),
        ("full_day", "Todo el día (8:00 - 18:00)"),
    ], required=True)

    need_payment = fields.Boolean(default=False)

    def action_create_booking(self):
        self.ensure_one()

        # Valida disponibilidad con tu método actual (o constraints)
        Booking = self.env["spoot.office.booking"].sudo()
        # Si intentas crear, tu constraint _check_no_overlap ya bloqueará duplicados
        booking = Booking.create({
            "office_id": self.office_id.id,
            "partner_id": self.partner_id.id,
            "date": self.date,
            "slot_type": self.slot_type,
            "need_payment": self.need_payment,
            "state": "pending_payment" if self.need_payment else "confirmed",
        })

        return {
            "type": "ir.actions.act_window",
            "res_model": "spoot.office.booking",
            "view_mode": "form",
            "res_id": booking.id,
            "target": "current",
        }
