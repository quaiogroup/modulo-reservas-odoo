# -*- coding: utf-8 -*-
import re
from odoo import api, fields, models


class OfficeResPartner(models.Model):
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
        "office.booking",
        "partner_id",
        string="Reservas Spoot",
    )

    spoot_booking_count = fields.Integer(
        string="Reservas",
        compute="_compute_spoot_booking_count",
        store=True,
    )

    spoot_active_subscription_id = fields.Many2one(
        "office.subscription",
        string="Plan activo",
        compute="_compute_spoot_live",
    )

    spoot_last_booking_date = fields.Date(
        string="Última reserva",
        compute="_compute_spoot_live",
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
            "res_model": "office.booking",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }

    @api.depends("spoot_booking_ids", "spoot_booking_ids.state")
    def _compute_spoot_booking_count(self):
        for rec in self:
            rec.spoot_booking_count = len(
                rec.spoot_booking_ids.filtered(lambda b: b.state != "cancelled")
            )

    def _compute_spoot_live(self):
        Sub = self.env["office.subscription"].sudo()
        for rec in self:
            bookings = rec.spoot_booking_ids.filtered(
                lambda b: b.state != "cancelled" and b.date
            )
            dates = bookings.mapped("date")
            rec.spoot_last_booking_date = max(dates) if dates else False
            active_sub = Sub.search([
                ("partner_id", "=", rec.id),
                ("state", "=", "active"),
            ], limit=1)
            rec.spoot_active_subscription_id = active_sub.id if active_sub else False
