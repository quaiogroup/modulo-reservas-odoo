# -*- coding: utf-8 -*-
import base64
import hashlib
import hmac

from odoo import http, _
from odoo.http import request


class SpootBoldPayController(http.Controller):
    """Controlador dedicado al flujo de pago Bold iniciado desde el portal."""

    def _icp(self):
        return request.env["ir.config_parameter"].sudo()

    def _get_bold_keys(self):
        ICP = self._icp()
        api_key    = (ICP.get_param("bold.api_key")    or "").strip()
        secret_key = (ICP.get_param("bold.secret_key") or "").strip()
        return api_key, secret_key

    def _integrity_signature(self, order_id: str, amount_int: int,
                              currency: str, secret_key: str) -> str:
        raw = f"{order_id}{amount_int}{currency}{secret_key}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # ── /my/office-bookings/<id>/pay ──────────────────────────────────────
    @http.route(
        "/my/office-bookings/<int:booking_id>/pay",
        type="http", auth="user", website=True, sitemap=False,
    )
    def pay_bold(self, booking_id, **kw):
        booking = (
            request.env["spoot.office.booking"]
            .sudo()
            .browse(booking_id)
            .exists()
        )
        if not booking or booking.partner_id != request.env.user.partner_id:
            return request.redirect("/my")

        # Solo reservas Bold pendientes de pago
        if booking.state == "cancelled" or booking.paid or booking.payment_mode != "bold":
            return request.redirect(f"/my/office-bookings/{booking.id}")

        api_key, secret_key = self._get_bold_keys()
        if not api_key or not secret_key:
            return request.render("spoot_office_booking.bold_error", {
                "booking": booking,
                "error": _("Faltan llaves de Bold. Configura bold.api_key y bold.secret_key."),
            })

        amount     = booking._get_amount_to_pay()
        amount_int = int(round(amount))
        currency   = booking._get_bold_currency_code()

        if amount_int < 1000:
            return request.render("spoot_office_booking.bold_error", {
                "booking": booking,
                "error": _("El monto mínimo para Bold es 1000 COP."),
            })

        order_id    = booking._ensure_bold_order_id()
        integrity   = self._integrity_signature(order_id, amount_int, currency, secret_key)
        base_url    = self._icp().get_param("web.base.url")
        redirect_url = f"{base_url}/bold/retorno"

        return request.render("spoot_office_booking.bold_pay_page", {
            "booking":              booking,
            "bold_api_key":         api_key,
            "bold_order_id":        order_id,
            "bold_amount":          amount_int,
            "bold_currency":        currency,
            "bold_integrity":       integrity,
            "bold_redirection_url": redirect_url,
            "bold_description": (
                f"Reserva oficina {booking.office_id.name} ({booking.slot_type})"
            ),
            "bold_render_mode": "embedded",
        })
