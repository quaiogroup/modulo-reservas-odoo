# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SpootOfficeBlock(models.Model):
    _name = "spoot.office.block"
    _description = "Bloqueo de fecha en oficina"
    _order = "date_start desc"

    name = fields.Char(string="Motivo", required=True)

    office_id = fields.Many2one(
        "spoot.office",
        string="Oficina",
        ondelete="cascade",
        help="Dejar vacío para bloquear todas las oficinas.",
    )

    date_start = fields.Date(string="Desde", required=True)
    date_end = fields.Date(string="Hasta", required=True)

    note = fields.Char(
        string="Nota para el usuario",
        help="Mensaje mostrado cuando se intenta reservar una fecha bloqueada.",
    )

    active = fields.Boolean(default=True)

    # ── Validación ────────────────────────────────────────────────────────────

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for rec in self:
            if rec.date_end < rec.date_start:
                raise ValidationError(
                    _("La fecha de fin debe ser igual o posterior a la de inicio.")
                )

    # ── Helpers públicos ─────────────────────────────────────────────────────

    @api.model
    def is_date_blocked(self, office_id, date):
        """
        Returns (blocked: bool, reason: str).
        Checks blocks that apply to `office_id` specifically OR to all offices
        (office_id = False).
        """
        block = self.sudo().search([
            ("active", "=", True),
            ("date_start", "<=", date),
            ("date_end", ">=", date),
            "|",
            ("office_id", "=", int(office_id)),
            ("office_id", "=", False),
        ], limit=1)

        if block:
            return True, block.note or block.name or _("Fecha no disponible")
        return False, ""

    @api.model
    def get_block_events(self, office_id, date_start, date_end):
        """
        Returns a list of calendar event dicts for all blocked dates in the
        given range (inclusive) for the given office.
        Used by the JS calendar endpoints.
        """
        blocks = self.sudo().search([
            ("active", "=", True),
            ("date_start", "<=", date_end),
            ("date_end", ">=", date_start),
            "|",
            ("office_id", "=", int(office_id)),
            ("office_id", "=", False),
        ])

        events = []
        for block in blocks:
            # Clip to the requested range so we don't return unnecessary data
            cur = max(block.date_start, date_start)
            end = min(block.date_end, date_end)
            while cur <= end:
                events.append({
                    "id":         f"block_{block.id}_{cur}",
                    "title":      block.name,
                    "date":       str(cur),
                    "note":       block.note or block.name,
                    "type":       "blocked",
                    "color":      "#9ca3af",
                    "url":        "#",
                    "slot":       "",
                    "slot_label": block.note or block.name,
                    "state":      "blocked",
                    "payment_mode": "",
                })
                cur += timedelta(days=1)

        return events
