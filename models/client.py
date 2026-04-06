# -*- coding: utf-8 -*-
import re
from odoo import api, fields, models


class SpootResPartner(models.Model):
    _inherit = "res.partner"

    whatsapp = fields.Char(
        string="WhatsApp",
        help="Número de WhatsApp con código de país. Ej: +573001234567",
    )

    whatsapp_url = fields.Char(
        string="Enlace WhatsApp",
        compute="_compute_whatsapp_url",
    )

    spoot_booking_ids = fields.One2many(
        "spoot.office.booking",
        "partner_id",
        string="Reservas Spoot",
    )

    spoot_booking_count = fields.Integer(
        string="Reservas",
        compute="_compute_spoot_stats",
        store=True,
    )

    spoot_active_subscription_id = fields.Many2one(
        "spoot.coworking.subscription",
        string="Plan activo",
        compute="_compute_spoot_stats",
    )

    spoot_last_booking_date = fields.Date(
        string="Última reserva",
        compute="_compute_spoot_stats",
    )

    @api.depends("whatsapp", "phone")
    def _compute_whatsapp_url(self):
        for rec in self:
            raw = rec.whatsapp or rec.phone or ""
            # keep only digits and leading +
            clean = re.sub(r"[^\d+]", "", raw).lstrip("+")
            rec.whatsapp_url = f"https://wa.me/{clean}" if clean else False

    def action_open_whatsapp(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": self.whatsapp_url,
            "target": "new",
        }

    def action_spoot_bookings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": f"Reservas de {self.name}",
            "res_model": "spoot.office.booking",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }

    @api.depends("spoot_booking_ids", "spoot_booking_ids.state", "spoot_booking_ids.date")
    def _compute_spoot_stats(self):
        Booking = self.env["spoot.office.booking"]
        Sub = self.env["spoot.coworking.subscription"]
        for rec in self:
            bookings = Booking.search([
                ("partner_id", "=", rec.id),
                ("state", "!=", "cancelled"),
            ])
            rec.spoot_booking_count = len(bookings)
            dates = bookings.filtered("date").mapped("date")
            rec.spoot_last_booking_date = max(dates) if dates else False
            active_sub = Sub.search([
                ("partner_id", "=", rec.id),
                ("state", "=", "active"),
            ], limit=1)
            rec.spoot_active_subscription_id = active_sub.id if active_sub else False
