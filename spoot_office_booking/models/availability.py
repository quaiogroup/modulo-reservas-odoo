from datetime import timedelta

from odoo import api, fields, models


class SpootOfficeAvailability(models.TransientModel):
    _name = "spoot.office.availability"
    _description = "Disponibilidad oficinas (vista)"
    _rec_name = "office_id"

    office_id = fields.Many2one("spoot.office", required=True, string="Oficina")
    week_start = fields.Date(required=True, default=lambda self: fields.Date.context_today(self))

    # 7 días * 2 mitades (mañana/tarde)
    d0_m_state = fields.Selection([("free","Libre"),("pending","Pendiente"),("busy","Ocupado")], compute="_compute_week", store=False)
    d0_a_state = fields.Selection([("free","Libre"),("pending","Pendiente"),("busy","Ocupado")], compute="_compute_week", store=False)
    d0_m_booking_id = fields.Many2one("spoot.office.booking", compute="_compute_week", store=False)
    d0_a_booking_id = fields.Many2one("spoot.office.booking", compute="_compute_week", store=False)

    d1_m_state = fields.Selection([("free","Libre"),("pending","Pendiente"),("busy","Ocupado")], compute="_compute_week", store=False)
    d1_a_state = fields.Selection([("free","Libre"),("pending","Pendiente"),("busy","Ocupado")], compute="_compute_week", store=False)
    d1_m_booking_id = fields.Many2one("spoot.office.booking", compute="_compute_week", store=False)
    d1_a_booking_id = fields.Many2one("spoot.office.booking", compute="_compute_week", store=False)

    d2_m_state = fields.Selection([("free","Libre"),("pending","Pendiente"),("busy","Ocupado")], compute="_compute_week", store=False)
    d2_a_state = fields.Selection([("free","Libre"),("pending","Pendiente"),("busy","Ocupado")], compute="_compute_week", store=False)
    d2_m_booking_id = fields.Many2one("spoot.office.booking", compute="_compute_week", store=False)
    d2_a_booking_id = fields.Many2one("spoot.office.booking", compute="_compute_week", store=False)

    d3_m_state = fields.Selection([("free","Libre"),("pending","Pendiente"),("busy","Ocupado")], compute="_compute_week", store=False)
    d3_a_state = fields.Selection([("free","Libre"),("pending","Pendiente"),("busy","Ocupado")], compute="_compute_week", store=False)
    d3_m_booking_id = fields.Many2one("spoot.office.booking", compute="_compute_week", store=False)
    d3_a_booking_id = fields.Many2one("spoot.office.booking", compute="_compute_week", store=False)

    d4_m_state = fields.Selection([("free","Libre"),("pending","Pendiente"),("busy","Ocupado")], compute="_compute_week", store=False)
    d4_a_state = fields.Selection([("free","Libre"),("pending","Pendiente"),("busy","Ocupado")], compute="_compute_week", store=False)
    d4_m_booking_id = fields.Many2one("spoot.office.booking", compute="_compute_week", store=False)
    d4_a_booking_id = fields.Many2one("spoot.office.booking", compute="_compute_week", store=False)

    d5_m_state = fields.Selection([("free","Libre"),("pending","Pendiente"),("busy","Ocupado")], compute="_compute_week", store=False)
    d5_a_state = fields.Selection([("free","Libre"),("pending","Pendiente"),("busy","Ocupado")], compute="_compute_week", store=False)
    d5_m_booking_id = fields.Many2one("spoot.office.booking", compute="_compute_week", store=False)
    d5_a_booking_id = fields.Many2one("spoot.office.booking", compute="_compute_week", store=False)

    d6_m_state = fields.Selection([("free","Libre"),("pending","Pendiente"),("busy","Ocupado")], compute="_compute_week", store=False)
    d6_a_state = fields.Selection([("free","Libre"),("pending","Pendiente"),("busy","Ocupado")], compute="_compute_week", store=False)
    d6_m_booking_id = fields.Many2one("spoot.office.booking", compute="_compute_week", store=False)
    d6_a_booking_id = fields.Many2one("spoot.office.booking", compute="_compute_week", store=False)

    @api.depends("office_id", "week_start")
    def _compute_week(self):
        Booking = self.env["spoot.office.booking"].sudo()
        for rec in self:
            if not rec.office_id or not rec.week_start:
                continue

            start = rec.week_start
            end = start + timedelta(days=7)

            bookings = Booking.search([
                ("office_id", "=", rec.office_id.id),
                ("date", ">=", start),
                ("date", "<", end),
                ("state", "!=", "cancelled"),
            ])

            # index: date -> slot -> booking
            idx = {}
            for b in bookings:
                idx.setdefault(b.date, {})
                # full_day bloquea ambas mitades
                if b.slot_type == "full_day":
                    idx[b.date]["morning"] = b
                    idx[b.date]["afternoon"] = b
                else:
                    idx[b.date][b.slot_type] = b

            def slot_state(booking):
                if not booking:
                    return ("free", False)
                if booking.state == "pending_payment" or (booking.payment_mode == "bold" and not booking.paid):
                    return ("pending", booking)
                return ("busy", booking)

            for i in range(7):
                day = start + timedelta(days=i)

                m_booking = idx.get(day, {}).get("morning")
                a_booking = idx.get(day, {}).get("afternoon")

                m_state, m_obj = slot_state(m_booking)
                a_state, a_obj = slot_state(a_booking)

                setattr(rec, f"d{i}_m_state", m_state)
                setattr(rec, f"d{i}_a_state", a_state)
                setattr(rec, f"d{i}_m_booking_id", m_obj.id if m_obj else False)
                setattr(rec, f"d{i}_a_booking_id", a_obj.id if a_obj else False)
