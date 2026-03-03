# -- coding: utf-8 --
import hmac
import hashlib
import json

from odoo import http, _
from odoo.http import request


class SpootBoldCheckoutController(http.Controller):

    def _get_bold_params(self):
        ICP = request.env["ir.config_parameter"].sudo()
        return {
            "public_key": ICP.get_param("bold.public_key") or "",
            "secret_key": ICP.get_param("bold.secret_key") or "",
            "test_mode": (ICP.get_param("bold.test_mode") or "False").lower() in ("1", "true", "yes", "y"),
        }

    def _bold_signature(self, secret_key, order_id, amount, currency):
        """
        Firma genérica HMAC-SHA256.
        OJO: puede que Bold use otro formato exacto (concatenación específica).
        Cuando me pegues el snippet/doc exacto, lo dejamos perfecto.
        """
        msg = f"{order_id}|{amount:.2f}|{currency}".encode("utf-8")
        return hmac.new(secret_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    @http.route("/my/office-bookings/<int:booking_id>/pay", type="http", auth="user", website=True)
    def booking_pay_bold(self, booking_id, **kw):
        booking = request.env["spoot.office.booking"].sudo().browse(booking_id)

        # Seguridad portal
        if not booking.exists() or booking.partner_id != request.env.user.partner_id:
            return request.redirect("/my")

        if booking.state == "cancelled":
            return request.redirect(f"/my/office-bookings/{booking_id}")

        if not booking.need_payment or booking.paid:
            return request.redirect(f"/my/office-bookings/{booking_id}")

        # Genera order_id y valores
        params = self._get_bold_params()
        if not params["public_key"] or not params["secret_key"]:
            return request.render("spoot_office_booking.website_bold_error", {
                "booking": booking,
                "error": _("Faltan llaves de Bold. Configura bold.public_key y bold.secret_key."),
            })

        order_id = booking._ensure_bold_order_id()
        amount = booking._get_bold_amount()
        currency = booking._get_bold_currency_code()

        if amount <= 0:
            return request.render("spoot_office_booking.website_bold_error", {
                "booking": booking,
                "error": _("El valor a pagar es 0. Revisa precios de la oficina."),
            })

        signature = self._bold_signature(params["secret_key"], order_id, amount, currency)

        values = {
            "booking": booking,
            "bold_public_key": params["public_key"],
            "bold_order_id": order_id,
            "bold_amount": f"{amount:.2f}",
            "bold_currency": currency,
            "bold_signature": signature,
            "bold_test_mode": params["test_mode"],
            # URLs de retorno/webhook (ajústalas si Bold pide campos específicos)
            "return_url": "/payment/bold/return",
        }

        return request.render("spoot_office_booking.website_bold_pay", values)

    @http.route("/payment/bold/return", type="http", auth="public", website=True, csrf=False, methods=["GET", "POST"])
    def bold_return(self, **data):
        # Return NO es confiable para confirmar, pero sirve para mostrar "gracias".
        # El que confirma es el webhook.
        return request.redirect("/payment/status")

    @http.route("/payment/bold/webhook", type="http", auth="public", csrf=False, methods=["POST"])
    def bold_webhook(self, **kw):
        """
        Bold te enviará un payload. Aquí lo lees, validas, y confirmas reserva.
        Lo importante: del payload sacar order_id y status.
        """
        raw = request.httprequest.data
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return "INVALID_JSON"

        # AJUSTA estos keys según el payload real de Bold:
        order_id = payload.get("order_id") or payload.get("reference") or payload.get("orderId")
        status = (payload.get("status") or payload.get("state") or "").upper()
        tx_id = payload.get("transaction_id") or payload.get("tx_id") or payload.get("transactionId")

        if not order_id:
            return "MISSING_ORDER_ID"

        booking = request.env["spoot.office.booking"].sudo().search([("bold_order_id", "=", order_id)], limit=1)
        if not booking:
            return "BOOKING_NOT_FOUND"

        # Regla: SOLO confirmas si está aprobado
        if status in ("APPROVED", "APROBADA", "PAID", "SUCCESS", "COMPLETED"):
            booking.action_mark_paid(tx_id=tx_id)
            return "OK"

        # Si quieres manejar rechazado:
        # if status in ("REJECTED", "FAILED", "CANCELLED"): ...
        return "IGNORED"