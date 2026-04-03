# -*- coding: utf-8 -*-
import base64
import hashlib
import hmac
import json

from odoo import http, _
from odoo.http import request


class SpootBoldController(http.Controller):

    def _icp(self):
        return request.env["ir.config_parameter"].sudo()

    def _get_bold_keys(self):
        ICP = self._icp()
        api_key = (ICP.get_param("bold.api_key") or "").strip()          # Llave de identidad
        secret_key = (ICP.get_param("bold.secret_key") or "").strip()    # Llave secreta
        return api_key, secret_key

    def _integrity_signature(self, order_id: str, amount_int: int, currency: str, secret_key: str) -> str:
        # SHA256("{orderId}{amount}{currency}{secretKey}")
        raw = f"{order_id}{amount_int}{currency}{secret_key}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _valid_webhook_signature(self, raw_body: bytes, received_sig: str, secret_key: str) -> bool:
        # Bold: base64(body) + HMAC-SHA256(hex) con secret_key; comparar con x-bold-signature
        # Nota: en ambiente de pruebas Bold usa llave vacía para firma. (ojo con esto en tu test_mode)
        encoded = base64.b64encode(raw_body)
        digest = hmac.new(secret_key.encode("utf-8"), encoded, hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, (received_sig or "").strip())

    @http.route("/my/office-bookings/<int:booking_id>/pay", type="http", auth="user", website=True, sitemap=False)
    def pay_bold(self, booking_id, **kw):
        booking = request.env["spoot.office.booking"].sudo().browse(booking_id).exists()
        if not booking or booking.partner_id != request.env.user.partner_id:
            return request.redirect("/my")

        if booking.state == "cancelled" or booking.paid or not booking.need_payment:
            return request.redirect(f"/my/office-bookings/{booking.id}")

        api_key, secret_key = self._get_bold_keys()
        if not api_key or not secret_key:
            return request.render("spoot_office_booking.bold_error", {
                "booking": booking,
                "error": _("Faltan llaves de Bold. Configura bold.api_key y bold.secret_key."),
            })

        # Monto: Bold espera entero en COP (sin decimales)
        amount = booking._get_amount_to_pay()
        amount_int = int(round(amount))
        currency = "COP"
        if amount_int < 1000:
            return request.render("spoot_office_booking.bold_error", {
                "booking": booking,
                "error": _("El monto mínimo para Bold es 1000 COP."),
            })

        # Order ID único (máx 60 chars, alfanumérico, _ y -)
        order_id = booking._ensure_bold_order_id()

        integrity = self._integrity_signature(order_id, amount_int, currency, secret_key)

        base_url = self._icp().get_param("web.base.url")
        redirection_url = f"{base_url}/bold/retorno"

        return request.render("spoot_office_booking.bold_pay_page", {
            "booking": booking,
            "bold_api_key": api_key,
            "bold_order_id": order_id,
            "bold_amount": amount_int,
            "bold_currency": currency,
            "bold_integrity": integrity,
            "bold_redirection_url": redirection_url,
            "bold_description": f"Reserva oficina {booking.office_id.name} ({getattr(booking, 'slot_type', '')})",
            "bold_render_mode": "embedded",
        })

    @http.route("/bold/retorno", type="http", auth="public", website=True, sitemap=False)
    def bold_return(self, **kw):
        # Bold añade: bold-order-id y bold-tx-status
        order_id = kw.get("bold-order-id") or kw.get("bold_order_id")
        tx_status = (kw.get("bold-tx-status") or "").upper()

        booking = request.env["spoot.office.booking"].sudo().search([("bold_order_id", "=", order_id)], limit=1) if order_id else None
        if booking:
            booking.sudo().write({
                "payment_state": "processing",
                "bold_payment_status": tx_status or "PROCESSING",
            })


        return request.render("spoot_office_booking.bold_return_page", {
            "booking": booking,
            "order_id": order_id,
            "tx_status": tx_status,
        })

    @http.route("/bold/webhook", type="http", auth="public", csrf=False, methods=["POST"], sitemap=False)
    def bold_webhook(self, **kw):
        api_key, secret_key = self._get_bold_keys()

        raw = request.httprequest.get_data()
        received_sig = request.httprequest.headers.get("x-bold-signature", "")

        if not secret_key or not self._valid_webhook_signature(raw, received_sig, secret_key):
            return request.make_response("Invalid signature", headers=[("Content-Type", "text/plain")], status=400)

        payload = json.loads(raw.decode("utf-8"))
        event_type = payload.get("type")
        data = payload.get("data", {}) or {}
        reference = (data.get("metadata") or {}).get("reference")  # tu order_id
        payment_id = data.get("payment_id")

        if not reference:
            return request.make_response("Missing reference", headers=[("Content-Type", "text/plain")], status=400)

        booking = request.env["spoot.office.booking"].sudo().search([("bold_order_id", "=", reference)], limit=1)
        if not booking:
            return request.make_response("Booking not found", headers=[("Content-Type", "text/plain")], status=404)

        if event_type == "SALE_APPROVED":
            booking.action_mark_paid(tx_id=payment_id) if hasattr(booking, "action_mark_paid") else booking.sudo().write({
                "paid": True,
                "payment_state": "paid",
                "bold_payment_status": "APPROVED",
                "bold_transaction_id": payment_id,
            })
        elif event_type == "SALE_REJECTED":
            booking.sudo().write({
                "payment_state": "rejected",
                "bold_payment_status": "REJECTED",
                "bold_transaction_id": payment_id,
            })
        else:
            booking.sudo().write({"bold_payment_status": event_type or "UNKNOWN"})

        return request.make_response("ok", headers=[("Content-Type", "text/plain")], status=200)