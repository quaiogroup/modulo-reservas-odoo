# -- coding: utf-8 --
from odoo import http, _
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.http import request
from odoo.fields import Datetime
from werkzeug.utils import redirect
from odoo.http import Response
import base64
import hmac
import hashlib
import json



class SpootOfficeWebsite(http.Controller):

    #GET -> type="http"
    @http.route(
        "/offices/<int:office_id>/events",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def office_events(self, office_id, start=None, end=None, **kw):
        if not start or not end:
            return request.make_json_response([])

        start_dt = Datetime.to_datetime(start)
        end_dt = Datetime.to_datetime(end)

        partner = request.env.user.partner_id

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
        } for b in bookings]

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
        } for e in my_events]

        return request.make_json_response(booking_events + calendar_events)

    @http.route("/offices", type="http", auth="public", website=True)
    def offices_list(self, **kwargs):
        offices = request.env["spoot.office"].sudo().search([("active", "=", True)])
        return request.render("spoot_office_booking.website_office_list", {"offices": offices})

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

            # Checkbox correcto
            need_payment = True

            if not date or not slot_type:
                return request.render(
                    "spoot_office_booking.website_office_detail",
                    {"office": office, "error": _("Debes seleccionar una fecha y una franja horaria.")},
                )

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

            booking = request.env["spoot.office.booking"].sudo().create({
                "office_id": office.id,
                "partner_id": partner.id,
                "date": date,
                "slot_type": slot_type,
                "need_payment": need_payment,
                "state": "pending_payment" if need_payment else "confirmed",
            })
            print(booking)

            # Sin pago -> confirmación normal
            if not need_payment:
                booking.sudo().action_send_emails()
                return request.render("spoot_office_booking.website_booking_thanks", {"booking": booking})

            # Con pago -> BOLD
            return redirect(f"/my/office-bookings/{booking.id}")

        return request.render("spoot_office_booking.website_office_detail", {"office": office})


class SpootOfficePortal(CustomerPortal):


    @http.route("/bold/retorno", type="http", auth="public", website=True, sitemap=False)
    def bold_return(self, **kw):
        order_id = kw.get("bold-order-id") or kw.get("bold_order_id")
        tx_status = (kw.get("bold-tx-status") or "").upper()

        booking = request.env["spoot.office.booking"].sudo().search([("bold_order_id", "=", order_id)], limit=1) if order_id else None
        if booking:
            booking.sudo().write({"bold_payment_status": tx_status or "PROCESSING"})
            return redirect(f"/my/office-bookings/{booking.id}")

        return redirect("/my/office-bookings")

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

        pager = portal_pager(url="/my/office-bookings", total=booking_count, page=page, step=20)

        bookings = Booking.search(domain, order="date desc", limit=20, offset=pager["offset"])
        bold_ui_map = {}

        ICP = request.env["ir.config_parameter"].sudo()
        api_key = (ICP.get_param("bold.api_key") or "").strip()
        secret_key = (ICP.get_param("bold.secret_key") or "").strip()
        base_url = ICP.get_param("web.base.url")

        print(api_key, secret_key)

        if api_key and secret_key:
            for b in bookings:
                if not (b.need_payment and not b.paid and b.state != "cancelled"):
                    continue

                amount_int = int(round(b._get_amount_to_pay()))
                currency = "COP"
                order_id = b._ensure_bold_order_id()
                integrity = hashlib.sha256(f"{order_id}{amount_int}{currency}{secret_key}".encode("utf-8")).hexdigest()

                bold_ui_map[b.id] = {
                    "api_key": api_key,
                    "order_id": order_id,
                    "amount": amount_int,
                    "currency": currency,
                    "integrity": integrity,
                    "redirection_url": f"{base_url}/bold/retorno",
                    "description": f"Reserva oficina {b.office_id.name} ({b.slot_type})",
                }
                

        values = self._prepare_portal_layout_values()
        values.update({
    "bookings": bookings,
    "page_name": "office_bookings",
    "pager": pager,
    "bold_ui_map": bold_ui_map,
})
        values.update({"dbg_api_len": len(api_key), "dbg_sec_len": len(secret_key)})
        return request.render("spoot_office_booking.portal_my_bookings", values)
    @http.route("/my/office-bookings/<int:booking_id>", type="http", auth="user", website=True)
    def portal_booking_detail(self, booking_id, **kw):
        booking = request.env["spoot.office.booking"].sudo().browse(booking_id).exists()
        if not booking or booking.partner_id != request.env.user.partner_id:
            return request.redirect("/my")

        values = self._prepare_portal_layout_values()
        values.update({"booking": booking, "page_name": "office_bookings"})

        if booking.need_payment and not booking.paid and booking.state != "cancelled":
            ICP = request.env["ir.config_parameter"].sudo()
            api_key = (ICP.get_param("bold.api_key") or "").strip()
            secret_key = (ICP.get_param("bold.secret_key") or "").strip()

            # Si faltan keys, no renderices el botón (o muestra error)
            if api_key and secret_key:
                amount_int = int(round(booking._get_amount_to_pay()))
                currency = "COP"
                order_id = booking._ensure_bold_order_id()
                integrity = hashlib.sha256(f"{order_id}{amount_int}{currency}{secret_key}".encode("utf-8")).hexdigest()

                base_url = (ICP.get_param("web.base.url") or "").strip()
                base_url = base_url.replace("http://", "https://")
                redirection_url = f"{base_url}/bold/retorno"

                values.update({
                    "bold_api_key": api_key,
                    "bold_order_id": order_id,
                    "bold_amount": amount_int,
                    "bold_currency": currency,
                    "bold_integrity": integrity,
                    "bold_redirection_url": redirection_url,
                    "bold_description": f"Reserva oficina {booking.office_id.name} ({booking.slot_type})",
                })

        return request.render("spoot_office_booking.portal_booking_detail", values)

    @http.route('/my/office-bookings/<int:booking_id>/cancel', type='http', auth='user', methods=['POST'], website=True)
    def portal_booking_cancel(self, booking_id, **kw):
        booking = request.env["spoot.office.booking"].sudo().browse(booking_id)
        if booking and booking.partner_id == request.env.user.partner_id:
            if booking.state != "cancelled" and not booking.paid:
                booking.write({"state": "cancelled"})
        return request.redirect("/my/office-bookings")
    
    print("==== HEADERS ====")
    print(dict(request.httprequest.headers))
    print("=================")
    
    @http.route("/bold/webhook", type="http", auth="public", csrf=False, methods=["POST"], sitemap=False)
    def bold_webhook(self, **kw):

        ICP = request.env["ir.config_parameter"].sudo()
        secret_key = ""
        #(ICP.get_param("bold.secret_key") or "").strip()

        raw = request.httprequest.get_data() or b""
        headers = request.httprequest.headers
        signature = headers.get("X-Bold-Signature") or headers.get("x-bold-signature")

        print("==== WEBHOOK DEBUG ====")
        print("SECRET_KEY:", repr(secret_key))
        print("RECEIVED_SIGNATURE:", repr(signature))
        print("RAW_BODY:", raw.decode("utf-8"))
        print("BASE64_BODY:", base64.b64encode(raw))
        print("=======================")

        #if not secret_key or not signature:
        if not signature:
            return Response("Missing signature", status=400)

        # EXACTAMENTE como Bold lo hace
        str_message = raw.decode("utf-8")
        encoded = base64.b64encode(str_message.encode("utf-8"))

        expected = hmac.new(
            key=secret_key.encode(),
            msg=encoded,
            digestmod=hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, signature):
            return Response("Invalid signature", status=400)

        # Firma válida → ahora sí procesamos
        payload = json.loads(str_message)

        event_type = payload.get("type")
        data = payload.get("data") or {}
        reference = (data.get("metadata") or {}).get("reference")
        payment_id = data.get("payment_id")

        if not reference:
            return Response("Missing reference", status=400)

        booking = request.env["spoot.office.booking"].sudo().search(
            [("bold_order_id", "=", reference)],
            limit=1
        )

        if not booking:
            return Response("Booking not found", status=404)

        if event_type == "SALE_APPROVED":
            booking.action_mark_paid(tx_id=payment_id)
        else:
            booking.sudo().write({
                "bold_payment_status": event_type
            })

        return Response("ok", status=200)