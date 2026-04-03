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
            self.sudo().write({
                "bold_order_id": f"SPPOT-BOOK-{self.id}-{uuid.uuid4().hex[:10]}"
            })
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

    # ── Analytics ─────────────────────────────────────────────────────────
    @api.model
    def get_analytics_data(self):
        import calendar as _cal
        from datetime import date, timedelta
        from collections import Counter

        today = date.today()
        MONTH_NAMES = ['Ene','Feb','Mar','Abr','May','Jun',
                       'Jul','Ago','Sep','Oct','Nov','Dic']
        C = 251.327  # circumference r=40

        # ── últimos 6 meses ────────────────────────────────────────────
        monthly = []
        for i in range(5, -1, -1):
            m, y = today.month - i, today.year
            while m <= 0:
                m += 12; y -= 1
            first = date(y, m, 1)
            last  = date(y, m, _cal.monthrange(y, m)[1])
            bk = self.search([('date', '>=', first), ('date', '<=', last)])
            revenue = sum(
                b.amount_total for b in bk
                if b.payment_mode == 'bold' and b.paid
            )
            monthly.append({
                'label':     f"{MONTH_NAMES[m-1]} {y}",
                'bookings':  len(bk.filtered(lambda b: b.state != 'cancelled')),
                'cancelled': len(bk.filtered(lambda b: b.state == 'cancelled')),
                'revenue':   revenue,
            })

        # ── este mes vs mes anterior ────────────────────────────────────
        fm = date(today.year, today.month, 1)
        lm_day = date(today.year, today.month,
                      _cal.monthrange(today.year, today.month)[1])
        this_bk = self.search([('date','>=',fm),('date','<=',lm_day),
                                ('state','!=','cancelled')])
        this_rev = sum(b.amount_total for b in this_bk
                       if b.payment_mode == 'bold' and b.paid)

        pm, py = today.month - 1, today.year
        if pm <= 0: pm += 12; py -= 1
        pfm = date(py, pm, 1)
        plm = date(py, pm, _cal.monthrange(py, pm)[1])
        prev_bk = self.search([('date','>=',pfm),('date','<=',plm),
                                ('state','!=','cancelled')])
        prev_rev = sum(b.amount_total for b in prev_bk
                       if b.payment_mode == 'bold' and b.paid)

        # ── ocupación por oficina (mes actual) ──────────────────────────
        offices = self.env['spoot.office'].search([('active','=',True)])
        total_slots = _cal.monthrange(today.year, today.month)[1] * 2
        office_stats = []
        for office in offices:
            bk = self.search([
                ('office_id','=', office.id),
                ('date','>=', fm), ('date','<=', lm_day),
                ('state','!=','cancelled'),
            ])
            consumed = sum(2 if b.slot_type == 'full_day' else 1 for b in bk)
            rate = round(consumed / total_slots * 100, 1) if total_slots else 0
            office_stats.append({
                'name': office.name, 'consumed': consumed,
                'total': total_slots, 'rate': rate,
            })
        office_stats.sort(key=lambda x: x['rate'], reverse=True)

        # ── distribución últimos 6 meses ───────────────────────────────
        m6, y6 = today.month - 5, today.year
        while m6 <= 0: m6 += 12; y6 -= 1
        all_bk = self.search([
            ('date', '>=', date(y6, m6, 1)),
            ('state', '!=', 'cancelled'),
        ])
        slots = {
            'morning':   len(all_bk.filtered(lambda b: b.slot_type == 'morning')),
            'afternoon': len(all_bk.filtered(lambda b: b.slot_type == 'afternoon')),
            'full_day':  len(all_bk.filtered(lambda b: b.slot_type == 'full_day')),
        }
        slots_total = sum(slots.values()) or 1
        payment = {
            'bold': len(all_bk.filtered(lambda b: b.payment_mode == 'bold')),
            'plan': len(all_bk.filtered(lambda b: b.payment_mode == 'plan')),
        }
        payment_total = sum(payment.values()) or 1

        # donut segments: (label, value, pct, color, arc, rotate)
        def build_donut(segments_def):
            out, cum = [], 0
            for label, val, total_val, color in segments_def:
                pct = round(val / (total_val or 1) * 100)
                arc = val / (total_val or 1) * C
                out.append({
                    'label': label, 'value': val, 'pct': pct,
                    'color': color, 'arc': arc, 'rotate': -90 + cum * 3.6,
                })
                cum += pct
            return out

        slots_donut = build_donut([
            ('Mañana',      slots['morning'],   slots_total, '#3b82f6'),
            ('Tarde',       slots['afternoon'], slots_total, '#22c55e'),
            ('Día completo',slots['full_day'],  slots_total, '#6366f1'),
        ])
        pay_donut = build_donut([
            ('Bold',  payment['bold'], payment_total, '#f59e0b'),
            ('Plan',  payment['plan'], payment_total, '#6366f1'),
        ])

        # ── top 5 clientes ─────────────────────────────────────────────
        counter = Counter(b.partner_id.id for b in all_bk)
        top_clients = []
        for pid, cnt in counter.most_common(5):
            partner = self.env['res.partner'].browse(pid)
            rev = sum(b.amount_total for b in all_bk
                      if b.partner_id.id == pid and b.payment_mode == 'bold' and b.paid)
            top_clients.append({'name': partner.name or '—', 'count': cnt, 'revenue': rev})

        return {
            'monthly':       monthly,
            'offices':       office_stats,
            'slots_donut':   slots_donut,
            'pay_donut':     pay_donut,
            'slots':         slots,
            'payment':       payment,
            'top_clients':   top_clients,
            'donut_circ':    C,
            'totals': {
                'this_bookings': len(this_bk),
                'this_revenue':  this_rev,
                'prev_bookings': len(prev_bk),
                'prev_revenue':  prev_rev,
            },
            'currency': self.env.company.currency_id.symbol or '$',
        }

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
    # POLÍTICA DE MODIFICACIÓN
    # -------------------------------------------------------------------------
    def _can_be_modified(self):
        """
        Returns (True, "") if the booking can still be modified or cancelled
        by the customer, or (False, reason) if the time window has closed.
        """
        self.ensure_one()
        if self.state == 'cancelled':
            return False, _("La reserva ya está cancelada.")
        limit = self.office_id.modification_limit_hours
        if limit and self.start_datetime:
            from datetime import datetime as _dt
            hours_left = (self.start_datetime - _dt.now()).total_seconds() / 3600
            if hours_left <= limit:
                return False, _(
                    "No es posible modificar ni cancelar esta reserva: "
                    "faltan menos de %d hora(s) para su inicio." % limit
                )
        return True, ""

    # -------------------------------------------------------------------------
    # DISPONIBILIDAD
    # -------------------------------------------------------------------------
    @api.model
    def get_availability(self, office_id, date_str, exclude_id=None):
        """
        Returns available/taken slots for office_id on date_str.
        exclude_id: booking id to ignore (used when rescheduling).
        """
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

        domain = [
            ("office_id", "=", int(office_id)),
            ("date", "=", date),
            ("state", "!=", "cancelled"),
        ]
        if exclude_id:
            domain.append(("id", "!=", int(exclude_id)))

        taken = self.sudo().search(domain).mapped("slot_type")

        taken_set = set(taken)
        available = []

        if "full_day" in taken_set:
            available = []
        else:
            if "morning" not in taken_set:
                available.append("morning")
            if "afternoon" not in taken_set:
                available.append("afternoon")
            if "morning" not in taken_set and "afternoon" not in taken_set:
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
    # STATS PARA DASHBOARD
    # -------------------------------------------------------------------------
    @api.model
    def get_dashboard_stats(self):
        import calendar as _cal
        from datetime import date as _date, timedelta as _td

        today = _date.today()
        week_start = today - _td(days=today.weekday())
        week_end   = week_start + _td(days=6)
        last_day   = _cal.monthrange(today.year, today.month)[1]
        month_start = today.replace(day=1)
        month_end   = today.replace(day=last_day)

        all_active = self.sudo().search([("state", "!=", "cancelled")])

        today_bk   = all_active.filtered(lambda b: b.date == today)
        week_bk    = all_active.filtered(lambda b: week_start <= b.date <= week_end)
        month_bk   = all_active.filtered(lambda b: month_start <= b.date <= month_end)
        pending_bk = all_active.filtered(lambda b: b.state == "pending_payment")

        upcoming = self.sudo().search([
            ("date", ">=", today),
            ("state", "in", ["confirmed", "pending_payment"]),
        ], order="date asc, slot_type asc", limit=8)

        _SLOT = {
            "morning":   "Mañana (8–12)",
            "afternoon": "Tarde (14–18)",
            "full_day":  "Día completo",
        }

        currency_symbol = (
            self.env.company.currency_id.symbol or "$"
        )

        return {
            "today_total":     len(today_bk),
            "today_confirmed": len(today_bk.filtered(lambda b: b.state == "confirmed")),
            "week_confirmed":  len(week_bk.filtered(lambda b: b.state == "confirmed")),
            "month_total":     len(month_bk),
            "pending_count":   len(pending_bk),
            "currency":        currency_symbol,
            "month_revenue":   sum(
                b.amount_total for b in month_bk
                if b.paid and b.payment_mode == "bold"
            ),
            "upcoming": [
                {
                    "id":           b.id,
                    "name":         b.name,
                    "office":       b.office_id.name,
                    "date":         fields.Date.to_string(b.date),
                    "slot":         _SLOT.get(b.slot_type, b.slot_type or ""),
                    "partner":      b.partner_id.name or "",
                    "state":        b.state,
                    "payment_mode": b.payment_mode or "bold",
                }
                for b in upcoming
            ],
        }

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
