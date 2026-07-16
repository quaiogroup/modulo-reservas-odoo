# -*- coding: utf-8 -*-
import re
from odoo import api, fields, models


class OfficeResPartner(models.Model):
    _inherit = "res.partner"

    # ── Identificación ────────────────────────────────────────────────
    sppot_document_type = fields.Selection([
        ("cc",  "Cédula de ciudadanía"),
        ("nit", "NIT / RUT"),
        ("ce",  "Cédula de extranjería"),
        ("pas", "Pasaporte"),
        ("ti",  "Tarjeta de identidad"),
        ("rc",  "Registro civil"),
        ("otro","Otro"),
    ], string="Tipo de documento")

    sppot_document_number = fields.Char(string="Número de documento")

    # ── Facturación ────────────────────────────────────────────────────
    sppot_billing_name = fields.Char(
        string="Razón social / Nombre facturación",
        help="Nombre o razón social que aparece en la factura. "
             "Si está vacío se usa el nombre del cliente.",
    )

    whatsapp = fields.Char(
        string="WhatsApp",
        help="Número de WhatsApp con código de país. Ej: +573001234567",
    )

    whatsapp_url = fields.Char(
        string="Enlace WhatsApp",
        compute="_compute_whatsapp_url",
    )

    sppot_booking_ids = fields.One2many(
        "office.booking",
        "partner_id",
        string="Reservas Sppot",
    )

    sppot_booking_count = fields.Integer(
        string="Reservas",
        compute="_compute_sppot_booking_count",
        store=True,
    )

    sppot_active_subscription_id = fields.Many2one(
        "office.subscription",
        string="Plan activo",
        compute="_compute_sppot_live",
    )

    sppot_last_booking_date = fields.Date(
        string="Última reserva",
        compute="_compute_sppot_live",
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

    def action_sppot_bookings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": f"Reservas de {self.name}",
            "res_model": "office.booking",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }

    @api.depends("sppot_booking_ids", "sppot_booking_ids.state")
    def _compute_sppot_booking_count(self):
        for rec in self:
            rec.sppot_booking_count = len(
                rec.sppot_booking_ids.filtered(lambda b: b.state != "cancelled")
            )

    def _compute_sppot_live(self):
        Sub = self.env["office.subscription"].sudo()
        for rec in self:
            bookings = rec.sppot_booking_ids.filtered(
                lambda b: b.state != "cancelled" and b.date
            )
            dates = bookings.mapped("date")
            rec.sppot_last_booking_date = max(dates) if dates else False
            active_sub = Sub.search([
                ("partner_id", "=", rec.id),
                ("state", "=", "active"),
            ], limit=1)
            rec.sppot_active_subscription_id = active_sub.id if active_sub else False
