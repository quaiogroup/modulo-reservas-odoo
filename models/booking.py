# -*- coding: utf-8 -*-
import base64
from datetime import datetime, time, timedelta

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

    payment_tx_id = fields.Many2one(
        "payment.transaction",
        string="Transacción de pago",
        copy=False,
        readonly=True,
    )

    start_datetime = fields.Datetime(string="Inicio", compute="_compute_datetimes", store=True)
    end_datetime = fields.Datetime(string="Fin", compute="_compute_datetimes", store=True)

    google_event_id = fields.Char(
        string="ID evento calendario (externo)",
        help="Se puede usar para sincronizar con Google Calendar u otros.",
    )

    notes = fields.Text(string="Notas internas")
    def _get_booking_amount(self):
        """Calcula el monto según la franja."""
        self.ensure_one()
        office = self.office_id

        if self.slot_type == "morning":
            return office.price_morning
        if self.slot_type == "afternoon":
            return office.price_afternoon
        return office.price_full_day

    def _create_payment_transaction(self):
        """Crea la transacción para esta reserva (referencia = booking.name)."""
        self.ensure_one()

        if not self.need_payment:
            raise ValidationError(_("Esta reserva no requiere pago."))
        if self.state == "cancelled":
            raise ValidationError(_("No puedes pagar una reserva cancelada."))
        if self.paid:
            raise ValidationError(_("Esta reserva ya está pagada."))

        provider = self.env["payment.provider"].sudo().search(
            [("code", "=", "epayco_spoot"), ("state", "=", "enabled")],
            limit=1,
        )
        if not provider:
            raise ValidationError(_("No hay un proveedor ePayco activo. Ve a Pagos y actívalo."))

        amount = self._get_booking_amount()
        if not amount or amount <= 0:
            raise ValidationError(_("El precio de la reserva es inválido. Revisa precios en la oficina."))

        # Opcional: reutilizar tx existente "pending" para no crear mil transacciones
        existing_tx = self.env["payment.transaction"].sudo().search([
            ("reference", "=", self.name),
            ("state", "in", ["draft", "pending", "authorized"]),
        ], limit=1)
        if existing_tx:
            return existing_tx

        tx = self.env["payment.transaction"].sudo().create({
            "provider_id": provider.id,
            "reference": self.name,  # 🔥 CLAVE para poder encontrar la reserva en el notify/return
            "amount": amount,
            "currency_id": self.currency_id.id if hasattr(self, "currency_id") else self.env.company.currency_id.id,
            "partner_id": self.partner_id.id,
            "operation": "online",
        })

        # Asegura estado pendiente de pago
        if self.state == "draft":
            self.write({"state": "pending_payment"})

        return tx

    # -------------------------------------------------------------------------
    # Compute: datetimes
    # -------------------------------------------------------------------------
    @api.depends("date", "slot_type")
    def _compute_datetimes(self):
        for rec in self:
            if not rec.date or not rec.slot_type:
                rec.start_datetime = False
                rec.end_datetime = False
                continue

            if rec.slot_type == "morning":
                start_t, end_t = time(8, 0), time(12, 0)
            elif rec.slot_type == "afternoon":
                start_t, end_t = time(14, 0), time(18, 0)
            else:
                start_t, end_t = time(8, 0), time(18, 0)

            rec.start_datetime = datetime.combine(rec.date, start_t)
            rec.end_datetime = datetime.combine(rec.date, end_t)

    # -------------------------------------------------------------------------
    # Compute: amount
    # -------------------------------------------------------------------------
    @api.depends("office_id", "slot_type", "currency_id")
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = rec._get_amount_to_pay()

    def _get_amount_to_pay(self):
        """Calcula el valor según la franja."""
        self.ensure_one()
        if not self.office_id:
            return 0.0
        if self.slot_type == "morning":
            return float(self.office_id.price_morning or 0.0)
        if self.slot_type == "afternoon":
            return float(self.office_id.price_afternoon or 0.0)
        return float(self.office_id.price_full_day or 0.0)

    # -------------------------------------------------------------------------
    # Anti-overlap
    # -------------------------------------------------------------------------
    @api.constrains("office_id", "date", "slot_type", "state")
    def _check_no_overlap(self):
        for rec in self:
            if not rec.office_id or not rec.date or not rec.slot_type:
                continue
            if rec.state == "cancelled":
                continue
            domain = [
                ("id", "!=", rec.id),
                ("office_id", "=", rec.office_id.id),
                ("date", "=", rec.date),
                ("slot_type", "=", rec.slot_type),
                ("state", "!=", "cancelled"),
            ]
            if self.sudo().search_count(domain):
                raise ValidationError(_("Esa franja ya está reservada. Elige otra."))

    # -------------------------------------------------------------------------
    # PAYMENT: referencia y creación de transacción
    # -------------------------------------------------------------------------
    def _get_payment_reference(self):
        """Referencia única de pago para enlazar reserva ↔ transacción."""
        self.ensure_one()
        # Ej: SPPOT-BOOK-15
        return f"SPPOT-BOOK-{self.id}"

    def _get_epayco_provider(self):
        """Obtiene provider ePayco habilitado para la compañía."""
        self.ensure_one()
        provider = self.env["payment.provider"].sudo().search(
            [
                ("code", "=", "epayco_spoot"),
                ("state", "=", "enabled"),
                ("company_id", "=", self.env.company.id),
            ],
            limit=1,
        )
        if not provider:
            raise UserError(_("No hay un proveedor ePayco habilitado para esta compañía."))
        return provider

    def _create_payment_transaction(self):
        """Crea (o reutiliza) la transacción asociada a la reserva."""
        self.ensure_one()

        if self.state == "cancelled":
            raise UserError(_("Esta reserva está cancelada."))

        if not self.need_payment:
            raise UserError(_("Esta reserva no requiere pago."))

        amount = self._get_amount_to_pay()
        if amount <= 0:
            raise UserError(_("El valor a pagar es 0. Revisa precios de la oficina."))

        # Si ya existe una tx activa, reúsala (evita duplicar pagos)
        if self.payment_tx_id and self.payment_tx_id.state in ("draft", "pending", "authorized"):
            return self.payment_tx_id

        provider = self._get_epayco_provider()

        # payment_method_id: tomamos el primero del provider (si tu provider define métodos)
        payment_method = provider.payment_method_ids[:1]
        if not payment_method:
            # No siempre es obligatorio dependiendo del flujo, pero en muchos casos sí.
            raise UserError(_("El proveedor ePayco no tiene métodos de pago configurados."))

        tx = self.env["payment.transaction"].sudo().create(
            {
                "provider_id": provider.id,
                "payment_method_id": payment_method.id,
                "amount": amount,
                "currency_id": self.currency_id.id,
                "partner_id": self.partner_id.id,
                "reference": self._get_payment_reference(),
                # Esto ayuda a volver a tu web después del pago (ajústalo a tu ruta real)
                "landing_route": "/payment/status",
            }
        )

        self.payment_tx_id = tx.id
        self.state = "pending_payment"
        return tx
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
    # PAYMENT: acción para iniciar pago (backend)
    # -------------------------------------------------------------------------
    def action_pay_now(self):
        """
        Acción backend: crea transacción y devuelve un action URL
        (útil si agregas un botón en el formulario de la reserva).
        """
        self.ensure_one()
        tx = self._create_payment_transaction()

        # En Odoo, normalmente el “render/redirect” se hace desde controladores web.
        # Pero para backend podemos mandar al usuario a un endpoint nuestro que inicie el pago.
        return {
            "type": "ir.actions.act_url",
            "url": f"/spoot/booking/{self.id}/pay",
            "target": "self",
        }
    def action_pay(self):
        self.ensure_one()

        provider = self.env["payment.provider"].sudo().search(
            [("code", "=", "epayco_spoot"), ("state", "=", "enabled")],
            limit=1,
        )

        if not provider:
            raise ValidationError("No hay proveedor ePayco activo.")

        tx = self.env["payment.transaction"].sudo().create({
            "amount": self._get_price(),
            "currency_id": self.env.company.currency_id.id,
            "provider_id": provider.id,
            "reference": self.name,  # 🔥 CLAVE
            "partner_id": self.partner_id.id,
            "operation": "online",
        })

        return provider._get_redirect_form(tx)


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
