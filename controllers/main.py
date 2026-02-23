# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.http import request
from odoo.fields import Datetime
from odoo.addons.payment import utils as payment_utils
from werkzeug.utils import redirect
from urllib.parse import urlencode



class SpootOfficeWebsite(http.Controller):
    # ------------------------------------------------------------------
    # DISPONIBILIDAD (LIVIANO) -> para el calendario simple por día/mes
    #   OJO: Este endpoint depende de tu método:
    #   spoot.office.booking.get_availability(office_id, day)
    # ------------------------------------------------------------------
    @http.route("/spoot/office/availability", type="json", auth="user", website=True)
    def spoot_office_availability(self, office_id=None, day=None, **kw):
        if not office_id or not day:
            return {"error": "missing_params"}

        try:
            office_id = int(office_id)
        except Exception:
            return {"error": "invalid_office_id"}

        data = request.env["spoot.office.booking"].sudo().get_availability(office_id, day)
        return data

    # ------------------------------------------------------------------
    # EVENTOS (si aún usas FullCalendar en algún lado)
    # ------------------------------------------------------------------
    @http.route(
        "/offices/<int:office_id>/events",
        type="json",
        auth="user",
        website=True,
    )
    def office_events(self, office_id, start=None, end=None, **kw):
        """
        Devuelve eventos para FullCalendar:
        - Reservas de la oficina (bloqueos)
        - Eventos del calendario del usuario
        """
        if not start or not end:
            return []

        # Convierte ISO → datetime
        start_dt = Datetime.to_datetime(start)
        end_dt = Datetime.to_datetime(end)

        partner = request.env.user.partner_id

        # 1) Reservas NO canceladas de la oficina (bloquean)
        Booking = request.env["spoot.office.booking"].sudo()
        bookings = Booking.search([
            ("office_id", "=", int(office_id)),
            ("state", "!=", "cancelled"),
            ("start_datetime", "<", end_dt),
            ("end_datetime", ">", start_dt),
        ])

        booking_events = [{
            "id": f"booking_{b.id}",
            "title": "Reservada",
            "start": b.start_datetime,
            "end": b.end_datetime,
            "allDay": False,
            "display": "block",
            "backgroundColor": "#dc3545",
            "borderColor": "#dc3545",
        } for b in bookings]

        # 2) Eventos del calendario del usuario (sus eventos)
        CalendarEvent = request.env["calendar.event"].sudo()
        my_events = CalendarEvent.search([
            ("partner_ids", "in", [partner.id]),
            ("start", "<", end_dt),
            ("stop", ">", start_dt),
        ])

        calendar_events = [{
            "id": f"calendar_{e.id}",
            "title": e.name or "Evento",
            "start": e.start,
            "end": e.stop,
            "allDay": bool(getattr(e, "allday", False)),
            "display": "auto",
            "backgroundColor": "#0d6efd",
            "borderColor": "#0d6efd",
        } for e in my_events]

        return booking_events + calendar_events

    # ------------------------------------------------------------------
    # LISTADO DE OFICINAS (PÚBLICO)
    # ------------------------------------------------------------------
    @http.route("/offices", type="http", auth="public", website=True)
    def offices_list(self, **kwargs):
        offices = request.env["spoot.office"].sudo().search([("active", "=", True)])
        return request.render("spoot_office_booking.website_office_list", {"offices": offices})

    # ------------------------------------------------------------------
    # DETALLE OFICINA + RESERVA
    # ------------------------------------------------------------------
    @http.route(
        "/offices/<model('spoot.office'):office>",
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
        csrf=False,
    )
    def office_detail(self, office, **post):
        partner = request.env.user.partner_id

        if request.httprequest.method == "POST":
            date = post.get("date")
            slot_type = post.get("slot_type")
            need_payment = bool(post.get("need_payment"))

            # 1) Validación básica
            if not date or not slot_type:
                return request.render(
                    "spoot_office_booking.website_office_detail",
                    {"office": office, "error": _("Debes seleccionar una fecha y una franja horaria.")},
                )

            # 2) Validación de disponibilidad REAL (seguridad backend)
            availability = request.env["spoot.office.booking"].sudo().get_availability(office.id, date)

            if "available" not in availability:
                return request.render(
                    "spoot_office_booking.website_office_detail",
                    {"office": office, "error": _("No se pudo validar disponibilidad. Intenta nuevamente.")},
                )

            if slot_type not in availability["available"]:
                return request.render(
                    "spoot_office_booking.website_office_detail",
                    {
                        "office": office,
                        "error": _("Esa franja ya no está disponible. Revisa el calendario y elige una opción libre."),
                    },
                )

            # 3) Crear reserva
            booking = request.env["spoot.office.booking"].sudo().create({
                "office_id": office.id,
                "partner_id": partner.id,
                "date": date,
                "slot_type": slot_type,
                "need_payment": need_payment,
                "state": "pending_payment" if need_payment else "confirmed",
            })

            # Si NO requiere pago: confirmas y envías correos
            if not need_payment:
                booking.sudo().action_send_emails()
                return request.render("spoot_office_booking.website_booking_thanks", {"booking": booking})

            # Si SÍ requiere pago: rediriges a /payment/pay
            amount = booking.sudo()._get_amount_to_pay()   # (lo creamos abajo en el modelo)
            currency = booking.sudo()._get_currency()

            access_token = payment_utils.generate_access_token(partner.id, amount, currency.id)

            params = {
                # Ojo: "reference" aquí es un PREFIJO, Odoo genera la referencia final.
                # Lo usamos para poder identificar la reserva después.
                "reference": f"BKG{booking.id}",
                "amount": amount,
                "currency_id": currency.id,
                "partner_id": partner.id,
                "company_id": (office.company_id.id if hasattr(office, "company_id") and office.company_id else request.env.company.id),
                "access_token": access_token,
            }

            return redirect("/payment/pay?" + urlencode(params))


        # GET
        return request.render("spoot_office_booking.website_office_detail", {"office": office})


# ----------------------------------------------------------------------
# PORTAL DEL CLIENTE
# ----------------------------------------------------------------------
class SpootOfficePortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "booking_count" in counters:
            values["booking_count"] = request.env["spoot.office.booking"].sudo().search_count(
                [("partner_id", "=", request.env.user.partner_id.id)]
            )
        return values

    @http.route(
        ["/my/office-bookings", "/my/office-bookings/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_bookings(self, page=1, **kw):
        partner = request.env.user.partner_id
        Booking = request.env["spoot.office.booking"].sudo()

        domain = [("partner_id", "=", partner.id)]
        booking_count = Booking.search_count(domain)

        pager = portal_pager(
            url="/my/office-bookings",
            total=booking_count,
            page=page,
            step=20,
        )

        bookings = Booking.search(
            domain,
            order="date desc",
            limit=20,
            offset=pager["offset"],
        )

        values = self._prepare_portal_layout_values()
        values.update({
            "bookings": bookings,
            "page_name": "office_bookings",
            "pager": pager,
        })

        return request.render("spoot_office_booking.portal_my_bookings", values)

    @http.route(
        "/my/office-bookings/<int:booking_id>",
        type="http",
        auth="user",
        website=True,
    )
    def portal_booking_detail(self, booking_id, **kw):
        booking = request.env["spoot.office.booking"].sudo().browse(booking_id)
        if not booking or booking.partner_id != request.env.user.partner_id:
            return request.redirect("/my")

        values = self._prepare_portal_layout_values()
        values.update({
            "booking": booking,
            "page_name": "office_bookings",
        })

        return request.render("spoot_office_booking.portal_booking_detail", values)

    @http.route(
        "/my/office-bookings/<int:booking_id>/cancel",
        type="http",
        auth="user",
        website=True,
    )
    def portal_booking_cancel(self, booking_id, **kw):
        booking = request.env["spoot.office.booking"].sudo().browse(booking_id)
        if booking and booking.partner_id == request.env.user.partner_id:
            if booking.state != "cancelled" and not booking.paid:
                booking.write({"state": "cancelled"})
        return request.redirect("/my/office-bookings")
    
    @http.route(
        "/my/office-bookings/<int:booking_id>/pay",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        csrf=False,
    )
    def portal_booking_pay(self, booking_id, **kw):
        booking = request.env["spoot.office.booking"].sudo().browse(booking_id)
        if not booking.exists() or booking.partner_id.id != request.env.user.partner_id.id:
            return request.redirect("/my/office-bookings")
        
        if booking.paid or booking.state == "cancelled":
            return request.redirect("/my/office-bookings/{booking.id}")
        
        tx = booking._create_payment_transaction()
        
        processing_values= tx._get_processing_values()
        return request.render("payment.payment_process", processing_values)
