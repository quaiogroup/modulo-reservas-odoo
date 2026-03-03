# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request


class SpootBoldController(http.Controller):

    @http.route("/my/office-bookings/<int:booking_id>/pay-bold", type="http", auth="user", website=True)
    def pay_bold(self, booking_id, **kw):
        booking = request.env["spoot.office.booking"].sudo().browse(booking_id)
        if not booking or booking.partner_id != request.env.user.partner_id:
            return request.redirect("/my/office-bookings")

        if booking.state == "cancelled":
            return request.redirect(f"/my/office-bookings/{booking.id}")
        if booking.paid:
            return request.redirect(f"/my/office-bookings/{booking.id}")

        # 1) Amount según franja
        amount = booking._get_amount_to_pay()
        if amount <= 0:
            return request.redirect(f"/my/office-bookings/{booking.id}")

        # Bold en la doc usa COP y amount como entero (ej: 30000) :contentReference[oaicite:2]{index=2}
        currency = "COP"
        amount_int = int(round(amount))

        # 2) Llaves (server-side)
        identity_key, secret_key = booking._get_bold_keys()

        # 3) Order ID único
        order_id = booking._get_or_create_bold_order_id()

        # 4) Hash de integridad (SHA256)
        integrity = booking._compute_bold_integrity_signature(order_id, amount_int, currency, secret_key)

        # 5) URL a donde Bold devuelve al final
        base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url")
        redirection_url = f"{base_url}/my/office-bookings/{booking.id}/bold-return"

        values = {
            "booking": booking,
            "bold_order_id": order_id,
            "bold_currency": currency,
            "bold_amount": amount_int,
            "bold_api_key": identity_key,          # Llave de identidad
            "bold_integrity": integrity,           # Hash
            "bold_redirection_url": redirection_url,
            "bold_description": f"Reserva oficina {booking.office_id.name} ({booking.slot_type})",
        }
        return request.render("spoot_office_booking.bold_pay_page", values)

    @http.route("/my/office-bookings/<int:booking_id>/bold-return", type="http", auth="user", website=True)
    def bold_return(self, booking_id, **kw):
        # Aquí, mínimo: mostrar al usuario "recibimos tu pago, estamos validando".
        # Si luego conectas API/webhook de Bold, en este punto confirmas (paid/state).
        booking = request.env["spoot.office.booking"].sudo().browse(booking_id)
        if booking and booking.partner_id == request.env.user.partner_id:
            # opcional: guardar algo que venga en kw
            booking.sudo().write({"bold_last_status": kw.get("status") or kw.get("payment_status") or ""})
        return request.redirect(f"/my/office-bookings/{booking_id}")