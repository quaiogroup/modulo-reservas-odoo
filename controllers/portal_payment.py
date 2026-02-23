# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class SpootBookingPaymentController(http.Controller):

    @http.route(
        "/my/office-bookings/<int:booking_id>/pay",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        csrf=False,
    )
    def portal_booking_pay(self, booking_id, **kw):
        Booking = request.env["spoot.office.booking"].sudo()
        booking = Booking.browse(booking_id)

        # Seguridad: que exista y sea del usuario
        if not booking.exists() or booking.partner_id.id != request.env.user.partner_id.id:
            return request.redirect("/my/office-bookings")

        # No permitir pagar si ya está pagada o cancelada
        if booking.paid or booking.state == "cancelled":
            return request.redirect(f"/my/office-bookings/{booking.id}")

        # Crea (o reutiliza) transacción y lanza flujo pago
        tx = booking._create_payment_transaction()

        # Render del flujo estándar de Odoo (pantalla de “pagar / redirigir”)
        processing_values = tx._get_processing_values()
        return request.render("payment.payment_process", processing_values)
