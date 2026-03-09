# -*- coding: utf-8 -*-
import base64
from datetime import datetime, time, timedelta
import hashlib

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class SpootOfficeBooking(models.Model):
    _name = "spoot.office.booking"
    _inherit = ["mail.thread"]
    _description = "Reserva de oficina"
    _order = "date, office_id, slot_type"
    

    name = fields.Char(
        string="Referencia",
        required=True,
        copy=False,
        default="Nueva reserva",
        tracking=True,
    )

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
        default=lambda self: self.env.company.currency_id.id,
        required=True,
    )

    amount_total = fields.Monetary(
        string="Valor a pagar",
        currency_field="currency_id",
        compute="_compute_amount_total",
        store=True,
    )

    start_datetime = fields.Datetime(string="Inicio", compute="_compute_datetimes", store=True)
    end_datetime = fields.Datetime(string="Fin", compute="_compute_datetimes", store=True)

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
    

    def _get_bold_currency_code(self):
        """Bold normalmente espera código ISO: COP, USD, etc."""
        self.ensure_one()
        return (self.currency_id and self.currency_id.name) or self.env.company.currency_id.name or "COP"

    def _get_bold_amount(self):
        """Monto según franja (usa tu lógica)."""
        self.ensure_one()
        return float(self._get_amount_to_pay() or 0.0)

    def _ensure_bold_order_id(self):
        """Crea un order_id estable por reserva."""
        self.ensure_one()
        if not self.bold_order_id:
            # Debe ser único. Puedes cambiar el prefijo.
            self.bold_order_id = f"SPPOT-BOOK-{self.id}"
        return self.bold_order_id

    def action_mark_paid(self, tx_id=None):
        """Marca la reserva pagada y confirmada (la llama el webhook)."""
        for rec in self:
            if rec.state == "cancelled":
                continue
            rec.write({
                "paid": True,
                "state": "confirmed",
                "bold_tx_id": tx_id or rec.bold_tx_id,
            })
    
    def _get_booking_amount(self):
        """Calcula el monto según la franja."""
        self.ensure_one()
        office = self.office_id

        if self.slot_type == "morning":
            return office.price_morning
        if self.slot_type == "afternoon":
            return office.price_afternoon
        return office.price_full_day
    
    def _get_amount_to_pay(self):
        """Monto que debe pagar la reserva."""
        self.ensure_one()
        return float(self._get_booking_amount() or 0.0)
    
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
    # DISPONIBILIDAD (igual a tu código)
    # -------------------------------------------------------------------------
    @api.model
    def get_availability(self, office_id, date_str):
        if not office_id or not date_str:
            return {"available": [], "taken": []}

        date = fields.Date.from_string(date_str)

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
