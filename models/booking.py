# -*- coding: utf-8 -*-
import base64
from datetime import datetime, time, timedelta
import hashlib
import logging
import uuid

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class SpootOfficeBooking(models.Model):
    _name = "spoot.office.booking"
    _inherit = ["mail.thread"]
    _description = "Reserva de oficina"
    _order = "date, office_id, slot_type"

    

    name = fields.Char(
        string="Referencia",
        required=True,
        copy=False,
        default="/",
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] in ('/', 'Nueva reserva', False):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('spoot.office.booking')
                    or '/'
                )
        return super().create(vals_list)

    office_id = fields.Many2one(
        "spoot.office",
        string="Oficina",
        required=True,
        tracking=True,
    )

    partner_id = fields.Many2one(
        "res.partner",
        string="Cliente",
        required=True,
        help="Persona que realiza la reserva.",
        tracking=True,
    )

    date = fields.Date(string="Fecha de reserva", required=True, tracking=True)

    slot_type = fields.Selection(
        [
            ("morning", "Mañana (8:00 - 12:00)"),
            ("afternoon", "Tarde (14:00 - 18:00)"),
            ("full_day", "Todo el día (8:00 - 18:00)"),
        ],
        string="Franja horaria",
        required=True,
        tracking=True,
    )

    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("pending_payment", "Pendiente de pago"),
            ("confirmed", "Confirmada"),
            ("cancelled", "Cancelada"),
        ],
        string="Estado",
        default="draft",
        tracking=True,
    )

    need_payment = fields.Boolean(
        string="Requiere pago",
        help="Indica si esta reserva debe ir asociada a un pago.",
        default=True,
        tracking=True,
    )

    paid = fields.Boolean(
        string="Pagado",
        help="Se marcará en verdadero cuando el pago esté realizado.",
        default=False,
        tracking=True,
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        default=lambda self: self.env.company.currency_id,
        required=True
    )

    amount_total = fields.Monetary(
        string="Valor a pagar",
        currency_field="currency_id",
        compute="_compute_amount_total",
        store=True,
    )

    @api.depends("slot_type", "office_id")
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = rec._get_amount_to_pay()

    start_datetime = fields.Datetime(string="Inicio", compute="_compute_datetimes", store=True)
    end_datetime = fields.Datetime(string="Fin", compute="_compute_datetimes", store=True)

    @api.depends("date", "slot_type")
    def _compute_datetimes(self):
        _slot_hours = {
            "morning":   (8, 0,  12, 0),
            "afternoon": (14, 0, 18, 0),
            "full_day":  (8, 0,  18, 0),
        }
        for rec in self:
            times = _slot_hours.get(rec.slot_type) if rec.slot_type else None
            if rec.date and times:
                sh, sm, eh, em = times
                rec.start_datetime = datetime.combine(rec.date, time(sh, sm))
                rec.end_datetime   = datetime.combine(rec.date, time(eh, em))
            else:
                rec.start_datetime = False
                rec.end_datetime   = False

    google_event_id = fields.Char(
        string="ID evento calendario (externo)",
        help="Se puede usar para sincronizar con Google Calendar u otros.",
    )

    notes = fields.Text(string="Notas internas")
    # ---------------------------
    # BOLD (checkout externo)
    # ---------------------------
    bold_order_id = fields.Char(string="Bold Order ID", copy=False, readonly=True)
    bold_tx_id = fields.Char(string="Bold Transaction ID", copy=False, readonly=True)
    bold_payment_status = fields.Char(string="Bold Payment Status", copy=False, readonly=True)

    # ---------------------------
    # PLAN (coworking balance)
    # ---------------------------
    payment_mode = fields.Selection(
        [
            ("bold", "Pago externo (Bold)"),
            ("plan", "Consumo de plan"),
        ],
        string="Modo de pago",
        default="bold",
        tracking=True,
    )

    subscription_id = fields.Many2one(
        "spoot.coworking.subscription",
        string="Plan consumido",
        readonly=True,
        ondelete="set null",
        copy=False,
    )

    plan_days_consumed = fields.Float(
        string="Días de plan consumidos",
        default=0.0,
        readonly=True,
        copy=False,
        digits=(6, 1),
    )

    # ── Email / reminder tracking ──────────────────────────────────
    reminder_sent = fields.Boolean(
        string="Recordatorio enviado",
        default=False,
        copy=False,
        help="Se marca en True cuando el cron de recordatorios ha enviado "
             "el correo de aviso previo a esta reserva.",
    )

    def _get_plan_days_cost(self):
        """Returns plan days cost for this booking's slot type: 0.5 or 1.0."""
        self.ensure_one()
        return 1.0 if self.slot_type == "full_day" else 0.5

    def action_confirm_with_plan(self, subscription):
        """
        Confirm this booking by consuming balance from the given subscription.
        Raises ValidationError if the plan is not active or has insufficient balance.
        Idempotent: if already confirmed via plan, does nothing.
        """
        self.ensure_one()

        if self.state == "confirmed" and self.payment_mode == "plan":
            _logger.info("[PLAN BOOKING] already confirmed via plan — skipping id=%s", self.id)
            return

        if subscription.state != "active":
            raise ValidationError(_("Tu plan no está activo."))

        from odoo.fields import Date as FDate
        if subscription.end_date and subscription.end_date < FDate.today():
            raise ValidationError(_("Tu plan ha vencido."))

        cost = self._get_plan_days_cost()

        if subscription.remaining_days < cost:
            raise ValidationError(_(
                "Saldo de plan insuficiente. Tienes %.1f día(s) disponibles "
                "y esta reserva requiere %.1f." % (subscription.remaining_days, cost)
            ))

        subscription.sudo().write({"remaining_days": subscription.remaining_days - cost})

        self.write({
            "payment_mode": "plan",
            "subscription_id": subscription.id,
            "plan_days_consumed": cost,
            "need_payment": False,
            "paid": True,
            "state": "confirmed",
        })

        _logger.info(
            "[PLAN BOOKING] booking id=%s confirmed via plan id=%s — "
            "cost=%.1f remaining_after=%.1f",
            self.id, subscription.id, cost, subscription.remaining_days,
        )

    def action_cancel_and_restore_plan(self):
        """
        Cancel booking and restore plan balance if it was paid via plan.
        Safe to call on already-cancelled bookings (no-op).
        """
        self.ensure_one()
        if self.state == "cancelled":
            return

        if (
            self.payment_mode == "plan"
            and self.subscription_id
            and self.plan_days_consumed > 0
        ):
            new_remaining = self.subscription_id.remaining_days + self.plan_days_consumed
            self.subscription_id.sudo().write({"remaining_days": new_remaining})
            _logger.info(
                "[PLAN BOOKING] cancelled booking id=%s — restored %.1f days "
                "to subscription id=%s (new remaining: %.1f)",
                self.id, self.plan_days_consumed,
                self.subscription_id.id, new_remaining,
            )

        self.write({"state": "cancelled"})
        # Notify both parties of the cancellation
        self._notify_customer("spoot_office_booking.mail_template_booking_cancelled_user")
        self._notify_admin("spoot_office_booking.mail_template_booking_cancelled_admin")

    def _get_bold_currency_code(self):
        """Bold normalmente espera código ISO: COP, USD, etc."""
        self.ensure_one()
        return (self.currency_id and self.currency_id.name) or self.env.company.currency_id.name or "COP"

    def _get_bold_amount(self):
        """Monto según franja (usa tu lógica)."""
        self.ensure_one()
        return float(self._get_amount_to_pay() or 0.0)

    def _ensure_bold_order_id(self):
        self.ensure_one()
        if not self.bold_order_id:
            self.bold_order_id = f"SPPOT-BOOK-{self.id}-{uuid.uuid4().hex[:10]}"
        return self.bold_order_id

    def action_mark_paid(self, tx_id=None):
        """Marca la reserva pagada y confirmada (la llama el webhook o el retorno de Bold).
        Idempotente: si ya está confirmada no reenvía correos.
        """
        for rec in self:
            if rec.state == "cancelled":
                continue
            # Guard against double email when both browser redirect and webhook fire
            already_confirmed = (rec.state == "confirmed")
            rec.write({
                "paid": True,
                "state": "confirmed",
                "bold_tx_id": tx_id or rec.bold_tx_id,
            })
            if not already_confirmed:
                rec._notify_customer("spoot_office_booking.mail_template_booking_confirmed_bold")
                rec._notify_admin("spoot_office_booking.mail_template_booking_confirmed_admin")
    
    def action_view_subscription(self):
        """Open the linked coworking subscription record (used by the smart button)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "spoot.coworking.subscription",
            "view_mode": "form",
            "res_id": self.subscription_id.id,
            "target": "current",
        }

    # ── Email notification helpers ────────────────────────────────────────
    def _notify_customer(self, template_xml_id):
        """Send a transactional email to the booking's customer partner."""
        self.ensure_one()
        if not self.partner_id.email:
            _logger.warning(
                "[NOTIFY] partner %s has no email — skipping template %s",
                self.partner_id.id, template_xml_id,
            )
            return
        try:
            template = self.env.ref(template_xml_id, raise_if_not_found=False)
            if template:
                template.sudo().send_mail(self.id, force_send=True)
                _logger.info("[NOTIFY] customer email sent — template=%s booking=%s", template_xml_id, self.id)
            else:
                _logger.warning("[NOTIFY] template not found: %s", template_xml_id)
        except Exception as exc:
            _logger.error("[NOTIFY] customer email FAILED — template=%s booking=%s error=%s",
                          template_xml_id, self.id, exc)

    def _notify_admin(self, template_xml_id):
        """Send a notification email to the configured administrator address."""
        self.ensure_one()
        admin_email = self._get_admin_email()
        if not admin_email:
            _logger.warning("[NOTIFY] no admin email configured — skipping template %s", template_xml_id)
            return
        try:
            template = self.env.ref(template_xml_id, raise_if_not_found=False)
            if template:
                template.sudo().send_mail(
                    self.id,
                    force_send=True,
                    email_values={"email_to": admin_email, "recipient_ids": []},
                )
                _logger.info("[NOTIFY] admin email sent — template=%s booking=%s to=%s",
                             template_xml_id, self.id, admin_email)
            else:
                _logger.warning("[NOTIFY] template not found: %s", template_xml_id)
        except Exception as exc:
            _logger.error("[NOTIFY] admin email FAILED — template=%s booking=%s error=%s",
                          template_xml_id, self.id, exc)

    # ── Scheduled reminder ────────────────────────────────────────────────
    @api.model
    def _cron_send_booking_reminders(self):
        """Daily cron: send a reminder email for every confirmed booking scheduled for tomorrow.
        Uses reminder_sent flag to guarantee exactly-once delivery.
        """
        from datetime import date, timedelta
        tomorrow = date.today() + timedelta(days=1)
        bookings = self.search([
            ("state", "=", "confirmed"),
            ("date", "=", tomorrow),
            ("reminder_sent", "=", False),
        ])
        _logger.info(
            "[CRON REMINDER] date=%s — found %d booking(s) to remind",
            tomorrow, len(bookings),
        )
        for booking in bookings:
            booking._notify_customer("spoot_office_booking.mail_template_booking_reminder")
            booking.write({"reminder_sent": True})
        if bookings:
            _logger.info("[CRON REMINDER] sent %d reminder(s)", len(bookings))

    def _get_booking_amount(self):
        """Calcula el monto según la franja."""
        self.ensure_one()
        office = self.office_id

        if self.slot_type == "morning":
            return office.price_morning
        if self.slot_type == "afternoon":
            return office.price_afternoon
        return office.price_full_day

    
    def action_pay_now(self):
        self.ensure_one()

        if self.state == "cancelled":
            raise ValidationError("Esta reserva está cancelada.")

        if self.paid:
            raise ValidationError("Esta reserva ya está pagada.")

        self._ensure_bold_order_id()

    def _get_currency(self):
        self.ensure_one()
        # Si tu oficina no tiene company_id, usa la company actual
        company = getattr(self.office_id, "company_id", False) or self.env.company
        return company.currency_id

    def _get_amount_to_pay(self):
        self.ensure_one()
        office = self.office_id
        if self.slot_type == "morning":
            return float(office.price_morning or 0.0)
        if self.slot_type == "afternoon":
            return float(office.price_afternoon or 0.0)
        return float(office.price_full_day or 0.0)

    
    
    # -------------------------------------------------------------------------
    # DISPONIBILIDAD 
    # -------------------------------------------------------------------------
    @api.model
    def get_availability(self, office_id, date_str):
        if not office_id or not date_str:
            return {"available": [], "taken": []}

        date = fields.Date.from_string(date_str)

        # Check admin blocks first
        blocked, reason = self.env["spoot.office.block"].is_date_blocked(office_id, date)
        if blocked:
            return {
                "available": [],
                "taken": [],
                "blocked": True,
                "block_reason": reason,
            }

        taken = self.sudo().search([
            ("office_id", "=", int(office_id)),
            ("date", "=", date),
            ("state", "!=", "cancelled"),
        ]).mapped("slot_type")

        taken_set = set(taken)
        available = []

        if "full_day" in taken_set:
            available = []
        else:
            if "morning" not in taken_set:
                available.append("morning")
            if "afternoon" not in taken_set:
                available.append("afternoon")
            if ("morning" not in taken_set) and ("afternoon" not in taken_set):
                available.append("full_day")

        return {"available": available, "taken": list(taken_set)}

    # -------------------------------------------------------------------------
    # MATRIZ ADMIN (igual a tu código)
    # -------------------------------------------------------------------------
    @api.model
    def get_admin_availability_matrix(self, date_start, date_end, office_ids=None):
        if isinstance(date_start, str):
            date_start = fields.Date.from_string(date_start)
        if isinstance(date_end, str):
            date_end = fields.Date.from_string(date_end)

        if office_ids:
            offices = self.env["spoot.office"].sudo().browse(office_ids)
        else:
            offices = self.env["spoot.office"].sudo().search([("active", "=", True)], order="name asc")

        days = []
        cur = date_start
        while cur <= date_end:
            days.append(cur)
            cur += timedelta(days=1)

        bookings = self.sudo().search([
            ("office_id", "in", offices.ids),
            ("date", ">=", date_start),
            ("date", "<=", date_end),
            ("state", "!=", "cancelled"),
        ])

        index = {}
        for b in bookings:
            key = (b.office_id.id, b.date)
            index.setdefault(key, {})
            index[key][b.slot_type] = b

        def seg_status(booking):
            if not booking:
                return {"status": "free", "booking_id": False}
            if booking.state == "pending_payment":
                return {"status": "pending", "booking_id": booking.id}
            if booking.state == "confirmed":
                return {"status": "busy", "booking_id": booking.id}
            return {"status": "pending", "booking_id": booking.id}

        rows = []
        for office in offices:
            row_days = []
            for d in days:
                day_key = (office.id, d)
                day_bookings = index.get(day_key, {})
                full = day_bookings.get("full_day")
                if full:
                    seg_m = seg_status(full)
                    seg_a = seg_status(full)
                else:
                    seg_m = seg_status(day_bookings.get("morning"))
                    seg_a = seg_status(day_bookings.get("afternoon"))

                row_days.append({
                    "date": fields.Date.to_string(d),
                    "segments": {"morning": seg_m, "afternoon": seg_a},
                })

            rows.append({"office_id": office.id, "office_name": office.name, "days": row_days})

        return {"days": [fields.Date.to_string(d) for d in days], "rows": rows}



    # -------------------------------------------------------------------------
    # Correo + ICS (para Google Calendar, Outlook, etc.)
    # -------------------------------------------------------------------------
    def _get_admin_email(self):
        """Obtiene correo de administración desde parámetro o empresa."""
        param = self.env["ir.config_parameter"].sudo()
        email = param.get_param("spoot_office_booking.admin_email")
        if not email:
            email = self.env.company.email or self.env.user.email
        return email

    def _generate_ics_content(self):
        """Genera contenido ICS simple para evento de calendario."""
        self.ensure_one()
        if not self.start_datetime or not self.end_datetime:
            return ""

        def dt_to_ics(dt):
            dt_utc = fields.Datetime.to_datetime(dt)
            return dt_utc.strftime("%Y%m%dT%H%M%SZ")

        dtstamp = dt_to_ics(fields.Datetime.now())
        dtstart = dt_to_ics(self.start_datetime)
        dtend = dt_to_ics(self.end_datetime)

        summary = f"Reserva oficina {self.office_id.name}"
        location = self.office_id.location or ""
        description = (
            f"Reserva realizada por {self.partner_id.name} "
            f"para el día {self.date} en franja {self.slot_type}."
        )

        ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//SPPOT//OfficeBooking//ES
BEGIN:VEVENT
UID:{self.id}@spoot.co
DTSTAMP:{dtstamp}
DTSTART:{dtstart}
DTEND:{dtend}
SUMMARY:{summary}
LOCATION:{location}
DESCRIPTION:{description}
END:VEVENT
END:VCALENDAR
"""
        return ics

    def _create_ics_attachment(self):
        self.ensure_one()
        ics_content = self._generate_ics_content()
        if not ics_content:
            return False

        data = base64.b64encode(ics_content.encode("utf-8"))
        attachment = self.env["ir.attachment"].create(
            {
                "name": f"reserva_oficina_{self.id}.ics",
                "type": "binary",
                "datas": data,
                "mimetype": "text/calendar",
                "res_model": self._name,
                "res_id": self.id,
            }
        )
        return attachment

    def action_send_emails(self):
        """Envía correos a cliente y admin con ICS adjunto."""
        for booking in self:
            ics_attachment = booking._create_ics_attachment()

            template_user = self.env.ref(
                "spoot_office_booking.mail_template_booking_user",
                raise_if_not_found=False,
            )
            template_admin = self.env.ref(
                "spoot_office_booking.mail_template_booking_admin",
                raise_if_not_found=False,
            )

            email_values = {}
            if ics_attachment:
                email_values["attachment_ids"] = [ics_attachment.id]

            if template_user:
                template_user.send_mail(
                    booking.id,
                    force_send=True,
                    email_values=email_values,
                )
            if template_admin:
                admin_email = booking._get_admin_email()
                if admin_email:
                    email_values_admin = dict(email_values)
                    email_values_admin["email_to"] = admin_email
                    template_admin.send_mail(
                        booking.id,
                        force_send=True,
                        email_values=email_values_admin,
                    )
