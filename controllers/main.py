# -- coding: utf-8 --
import base64
import hashlib
import hmac
import json
import logging

from markupsafe import Markup
from werkzeug.utils import redirect

from odoo import http, _
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.fields import Date, Datetime
from odoo.http import request, Response

_logger = logging.getLogger(__name__)



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

        # Look up active subscription once — used for both GET and POST
        subscription = request.env["spoot.coworking.subscription"].sudo().search([
            ("partner_id", "=", partner.id),
            ("state", "=", "active"),
        ], limit=1) or False

        def _render_detail(error=None):
            return request.render("spoot_office_booking.website_office_detail", {
                "office": office,
                "subscription": subscription,
                "error": error,
            })

        if request.httprequest.method == "POST":
            date = post.get("date")
            slot_type = post.get("slot_type")
            payment_mode = post.get("payment_mode", "bold")  # 'plan' or 'bold'

            if not date or not slot_type:
                return _render_detail(_("Debes seleccionar una fecha y una franja horaria."))

            availability = request.env["spoot.office.booking"].sudo().get_availability(office.id, date)
            if "available" not in availability:
                return _render_detail(_("No se pudo validar disponibilidad. Intenta nuevamente."))

            if slot_type not in availability["available"]:
                return _render_detail(_("Esa franja ya no está disponible. Revisa el calendario y elige una opción libre."))

            _logger.info(
                "[BOOKING POST] date=%s slot_type=%s payment_mode=%s all_post=%s",
                date, slot_type, payment_mode, dict(post),
            )

            # ── PLAN MODE ──────────────────────────────────────────────────
            if payment_mode == "plan":
                if not subscription:
                    return _render_detail(_("No tienes un plan activo para usar como pago."))

                cost = 1.0 if slot_type == "full_day" else 0.5
                if subscription.remaining_days < cost:
                    return _render_detail(_(
                        "Saldo de plan insuficiente. Tienes %.1f día(s) disponibles "
                        "y esta reserva requiere %.1f." % (subscription.remaining_days, cost)
                    ))

                new_remaining = subscription.remaining_days - cost
                booking = request.env["spoot.office.booking"].sudo().create({
                    "office_id": office.id,
                    "partner_id": partner.id,
                    "date": date,
                    "slot_type": slot_type,
                    "need_payment": False,
                    "state": "confirmed",
                    "payment_mode": "plan",
                    "paid": True,
                    "subscription_id": subscription.id,
                    "plan_days_consumed": cost,
                })
                subscription.sudo().write({"remaining_days": new_remaining})
                _logger.info(
                    "[PLAN BOOKING] booking id=%s confirmed — slot=%s cost=%.1f "
                    "remaining_after=%.1f subscription=%s",
                    booking.id, slot_type, cost, new_remaining, subscription.id,
                )
                # Notify customer (plan confirmation) and admin (new booking)
                booking._notify_customer("spoot_office_booking.mail_template_booking_confirmed_plan")
                booking._notify_admin("spoot_office_booking.mail_template_booking_new_admin")
                return request.render("spoot_office_booking.website_booking_thanks", {"booking": booking})

            # ── BOLD PAYMENT MODE ──────────────────────────────────────────
            booking = request.env["spoot.office.booking"].sudo().create({
                "office_id": office.id,
                "partner_id": partner.id,
                "date": date,
                "slot_type": slot_type,
                "need_payment": True,
                "state": "pending_payment",
                "payment_mode": "bold",
            })
            # Notify customer (pending payment) and admin (new booking)
            booking._notify_customer("spoot_office_booking.mail_template_booking_pending_payment")
            booking._notify_admin("spoot_office_booking.mail_template_booking_new_admin")
            return redirect(f"/my/office-bookings/{booking.id}")

        return _render_detail()


class SpootOfficePortal(CustomerPortal):

    # Status values Bold sends as bold-tx-status in the browser redirect
    _BOLD_APPROVED_STATUSES = {"APPROVED", "SALE_APPROVED", "PAID", "SUCCESS", "COMPLETED"}

    # ── internal helper ────────────────────────────────────────────────────

    def _find_bold_record(self, order_id):
        """
        Given a Bold order_id, return (record, record_type) where record_type
        is 'booking' or 'subscription'.  Uses the SPPOT-BOOK-/SPPOT-PLAN- prefix
        to route to the correct model; falls back to searching both.
        Returns (None, None) if nothing is found.
        """
        if not order_id:
            return None, None

        if order_id.startswith("SPPOT-BOOK-"):
            rec = request.env["spoot.office.booking"].sudo().search(
                [("bold_order_id", "=", order_id)], limit=1
            )
            return (rec or None), "booking"

        if order_id.startswith("SPPOT-PLAN-"):
            rec = request.env["spoot.coworking.subscription"].sudo().search(
                [("bold_order_id", "=", order_id)], limit=1
            )
            return (rec or None), "subscription"

        # No recognized prefix — try both models
        rec = request.env["spoot.office.booking"].sudo().search(
            [("bold_order_id", "=", order_id)], limit=1
        )
        if rec:
            return rec, "booking"

        rec = request.env["spoot.coworking.subscription"].sudo().search(
            [("bold_order_id", "=", order_id)], limit=1
        )
        if rec:
            return rec, "subscription"

        return None, None

    # ── browser redirect from Bold after checkout ──────────────────────────

    @http.route("/bold/retorno", type="http", auth="public", website=True, sitemap=False)
    def bold_return(self, **kw):
        order_id = kw.get("bold-order-id") or kw.get("bold_order_id")
        tx_status = (kw.get("bold-tx-status") or "").upper()
        tx_id = kw.get("bold-tx-id") or kw.get("bold_tx_id") or None

        _logger.info(
            "[BOLD RETORNO] order_id=%s tx_status=%s tx_id=%s all_params=%s",
            order_id, tx_status, tx_id, dict(kw),
        )

        record, record_type = self._find_bold_record(order_id)

        if not record:
            _logger.warning("[BOLD RETORNO] no record found for order_id=%s", order_id)
            return redirect("/my")

        _logger.info(
            "[BOLD RETORNO] found %s id=%s",
            record_type, record.id,
        )

        if tx_status in self._BOLD_APPROVED_STATUSES:
            record.action_mark_paid(tx_id=tx_id)
            _logger.info(
                "[BOLD RETORNO] action_mark_paid called — %s id=%s",
                record_type, record.id,
            )
        else:
            record.sudo().write({"bold_payment_status": tx_status or "PROCESSING"})
            _logger.info(
                "[BOLD RETORNO] non-approved status=%s written to %s id=%s",
                tx_status, record_type, record.id,
            )

        if record_type == "booking":
            return redirect(f"/my/office-bookings/{record.id}")
        return redirect("/my/coworking")

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
        base_url = (ICP.get_param("web.base.url") or "").strip().replace("http://", "https://")

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
            if booking.state != "cancelled":
                if booking.payment_mode == "plan":
                    # Restore plan balance before cancelling
                    booking.sudo().action_cancel_and_restore_plan()
                elif not booking.paid:
                    # Regular unpaid Bold booking — cancel directly and notify
                    booking.write({"state": "cancelled"})
                    booking._notify_customer("spoot_office_booking.mail_template_booking_cancelled_user")
                    booking._notify_admin("spoot_office_booking.mail_template_booking_cancelled_admin")
                # Bold-paid bookings cannot be self-cancelled (would require a refund)
        return request.redirect("/my/office-bookings")
    

    
    @http.route("/bold/webhook", type="http", auth="public", csrf=False, methods=["POST"], sitemap=False)
    def bold_webhook(self, **kw):
        ICP = request.env["ir.config_parameter"].sudo()
        secret_key = (ICP.get_param("bold.secret_key") or "").strip()

        raw = request.httprequest.get_data() or b""
        headers = request.httprequest.headers
        content_type = headers.get("Content-Type", "")
        signature = headers.get("X-Bold-Signature") or headers.get("x-bold-signature")

        _logger.info("==== BOLD WEBHOOK RECEIVED ====")
        _logger.info("Content-Type: %s", content_type)
        _logger.info("X-Bold-Signature: %s", signature)
        _logger.info("secret_key configured: %s", bool(secret_key))
        _logger.info("raw body (%d bytes): %s", len(raw), raw[:500])

        if not raw:
            _logger.error("[BOLD WEBHOOK] empty body received")
            return Response("Empty body", status=400)

        str_message = raw.decode("utf-8")

        # Signature validation — only enforce if a secret key is configured
        if secret_key:
            if not signature:
                _logger.error("[BOLD WEBHOOK] missing X-Bold-Signature header")
                return Response("Missing signature", status=400)

            # Bold signs: HMAC-SHA256(base64(raw_body), secret_key)
            encoded = base64.b64encode(raw)
            expected = hmac.new(
                key=secret_key.encode("utf-8"),
                msg=encoded,
                digestmod=hashlib.sha256,
            ).hexdigest()

            _logger.info("[BOLD WEBHOOK] expected sig: %s", expected)
            _logger.info("[BOLD WEBHOOK] received sig: %s", signature)

            if not hmac.compare_digest(expected, signature):
                _logger.error("[BOLD WEBHOOK] signature mismatch — rejecting")
                return Response("Invalid signature", status=400)

            _logger.info("[BOLD WEBHOOK] signature valid")
        else:
            _logger.warning("[BOLD WEBHOOK] no secret_key configured — skipping signature check")

        # Parse payload
        try:
            payload = json.loads(str_message)
        except Exception as e:
            _logger.error("[BOLD WEBHOOK] JSON parse error: %s", e)
            return Response("Invalid JSON", status=400)

        _logger.info("[BOLD WEBHOOK] parsed payload: %s", payload)

        event_type = payload.get("type") or ""
        data = payload.get("data") or {}

        # Bold Smart Checkout payload:
        #   data.order.id  → the reference we sent (bold_order_id)
        #   data.payment.id → Bold transaction id
        # Fallback: older format uses data.metadata.reference
        order_data = data.get("order") or {}
        payment_data = data.get("payment") or {}

        reference = (
            order_data.get("id")
            or (data.get("metadata") or {}).get("reference")
            or data.get("reference")
        )
        payment_id = payment_data.get("id") or data.get("payment_id")

        _logger.info(
            "[BOLD WEBHOOK] event_type=%s reference=%s payment_id=%s",
            event_type, reference, payment_id,
        )

        if not reference:
            _logger.error("[BOLD WEBHOOK] could not extract order reference from payload")
            return Response("Missing reference", status=400)

        record, record_type = self._find_bold_record(reference)

        if not record:
            _logger.error("[BOLD WEBHOOK] no record found for bold_order_id=%s", reference)
            return Response("Record not found", status=404)

        _logger.info(
            "[BOLD WEBHOOK] found %s id=%s",
            record_type, record.id,
        )

        approved_events = {"SALE_APPROVED", "APPROVED", "PAYMENT_APPROVED"}
        if event_type.upper() in approved_events:
            record.action_mark_paid(tx_id=payment_id)
            _logger.info(
                "[BOLD WEBHOOK] action_mark_paid executed — %s id=%s",
                record_type, record.id,
            )
        else:
            record.sudo().write({"bold_payment_status": event_type})
            _logger.info(
                "[BOLD WEBHOOK] non-approval event=%s written to %s id=%s",
                event_type, record_type, record.id,
            )

        return Response("ok", status=200)
    
    @http.route("/coworking/plans", type="http", auth="user", website=True)
    def coworking_plans(self, **kwargs):
        plans = request.env["spoot.coworking.plan"].sudo().search([("active", "=", True)])
        partner = request.env.user.partner_id
        active_subscription = request.env["spoot.coworking.subscription"].sudo().search([
            ("partner_id", "=", partner.id),
            ("state", "=", "active"),
        ], limit=1) or False
        return request.render("spoot_office_booking.coworking_plans_page", {
            "plans": plans,
            "active_subscription": active_subscription,
        })
    
    @http.route("/coworking/checkout/<int:plan_id>", type="http", auth="user", website=True)
    def coworking_checkout(self, plan_id, **kwargs):
        plan = request.env["spoot.coworking.plan"].sudo().browse(plan_id)
        if not plan.exists() or not plan.active:
            return redirect("/coworking/plans")

        partner = request.env.user.partner_id

        # ── Hard backend block: user already has an active plan ───────
        active_subscription = request.env["spoot.coworking.subscription"].sudo().search([
            ("partner_id", "=", partner.id),
            ("state", "=", "active"),
        ], limit=1) or False

        if active_subscription:
            _logger.info(
                "[PLAN CHECKOUT] BLOCKED — partner %s already has active "
                "subscription %s ('%s'). No new record created.",
                partner.id, active_subscription.id, active_subscription.plan_id.name,
            )
            # Render checkout template with the blocking flag — no pending record created
            return request.render("spoot_office_booking.coworking_checkout_page", {
                "plan": plan,
                "active_subscription": active_subscription,
            })

        # Find an existing pending subscription for this partner+plan, or create one.
        # This prevents duplicate pending records if the user refreshes the page.
        Subscription = request.env["spoot.coworking.subscription"].sudo()
        subscription = Subscription.search([
            ("partner_id", "=", partner.id),
            ("plan_id", "=", plan.id),
            ("state", "=", "pending_payment"),
        ], limit=1)

        if not subscription:
            # Placeholder dates — will be set properly in action_mark_paid()
            today = Date.today()
            subscription = Subscription.create({
                "partner_id": partner.id,
                "plan_id": plan.id,
                "state": "pending_payment",
                "start_date": today,
                "end_date": today,
                "total_days": plan.days_included,
                "remaining_days": plan.days_included,
            })
            _logger.info(
                "[BOLD PLAN CHECKOUT] created pending subscription id=%s "
                "partner=%s plan=%s",
                subscription.id, partner.id, plan.name,
            )
        else:
            _logger.info(
                "[BOLD PLAN CHECKOUT] reusing existing pending subscription id=%s "
                "partner=%s plan=%s",
                subscription.id, partner.id, plan.name,
            )

        values = {"plan": plan, "subscription": subscription}

        ICP = request.env["ir.config_parameter"].sudo()
        api_key = (ICP.get_param("bold.api_key") or "").strip()
        secret_key = (ICP.get_param("bold.secret_key") or "").strip()

        if api_key and secret_key:
            amount_int = int(round(float(plan.price)))
            currency = (plan.currency_id.name or "COP").upper()
            order_id = subscription._ensure_bold_order_id()
            integrity = hashlib.sha256(
                f"{order_id}{amount_int}{currency}{secret_key}".encode("utf-8")
            ).hexdigest()

            base_url = (ICP.get_param("web.base.url") or "").strip().replace("http://", "https://")

            values.update({
                "bold_api_key": api_key,
                "bold_order_id": order_id,
                "bold_amount": amount_int,
                "bold_currency": currency,
                "bold_integrity": integrity,
                "bold_redirection_url": f"{base_url}/bold/retorno",
                "bold_description": f"Plan coworking: {plan.name}",
            })

            _logger.info(
                "[BOLD PLAN CHECKOUT] Bold data ready — subscription_id=%s "
                "order_id=%s amount=%s currency=%s",
                subscription.id, order_id, amount_int, currency,
            )
        else:
            _logger.warning(
                "[BOLD PLAN CHECKOUT] Bold API key / secret not configured — "
                "payment button will not render"
            )

        return request.render("spoot_office_booking.coworking_checkout_page", values)

    @http.route(['/my/coworking'], type='http', auth="user", website=True)
    def my_coworking_dashboard(self, **kwargs):
        partner = request.env.user.partner_id

        subscription = request.env['spoot.coworking.subscription'].sudo().search([
            ('partner_id', '=', partner.id),
            ('state', '=', 'active')
        ], limit=1)

        bookings = request.env['spoot.office.booking'].sudo().search([
            ('partner_id', '=', partner.id)
        ], order="date desc")

        days_used = 0
        days_pct = 0
        if subscription and subscription.total_days:
            days_used = subscription.total_days - subscription.remaining_days
            days_pct = int(round(days_used * 100.0 / subscription.total_days))

        # ── Build calendar event data for the JS widget ───────────────
        _SLOT_LABELS = {
            'morning': 'Mañana (8-12)',
            'afternoon': 'Tarde (14-18)',
            'full_day': 'Día completo',
        }
        _STATE_COLORS = {
            # confirmed via plan → emerald green
            # confirmed via bold → blue
            'pending_payment': '#f59e0b',
            'cancelled':       '#9ca3af',
            'draft':           '#6b7280',
        }

        calendar_events = []
        for b in bookings:
            if b.state == 'confirmed':
                color = '#10b981' if b.payment_mode == 'plan' else '#3b82f6'
            else:
                color = _STATE_COLORS.get(b.state, '#6b7280')

            calendar_events.append({
                'id':         b.id,
                'title':      b.office_id.name or 'Reserva',
                'date':       str(b.date) if b.date else None,
                'slot':       b.slot_type or '',
                'slot_label': _SLOT_LABELS.get(b.slot_type, b.slot_type or ''),
                'state':      b.state or '',
                'payment_mode': b.payment_mode or 'bold',
                'color':      color,
                'url':        '/my/office-bookings/%d' % b.id,
            })

        # Markup tells QWeb this string is already safe (no extra HTML-escaping)
        safe_json = json.dumps(calendar_events, ensure_ascii=True)
        safe_json = safe_json.replace('</', '<\\/')   # prevent </script> injection

        values = self._prepare_portal_layout_values()
        values.update({
            'subscription': subscription,
            'bookings': bookings,
            'today': Date.today(),
            'page_name': 'coworking',
            'booking_total': len(bookings),
            'booking_confirmed': len(bookings.filtered(lambda b: b.state == 'confirmed')),
            'booking_pending': len(bookings.filtered(lambda b: b.state == 'pending_payment')),
            'booking_cancelled': len(bookings.filtered(lambda b: b.state == 'cancelled')),
            'days_used': days_used,
            'days_pct': days_pct,
            'calendar_events_json': Markup(safe_json),
        })
        return request.render("spoot_office_booking.my_coworking_dashboard", values)