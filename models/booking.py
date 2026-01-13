import base64
from datetime import datetime, time

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class SpootOfficeBooking(models.Model):
    _name = "spoot.office.booking"
    _description = "Reserva de oficina"
    _order = "date, office_id, slot_type"

    name = fields.Char(
        string="Referencia",
        required=True,
        copy=False,
        default="Nueva reserva",
    )

    office_id = fields.Many2one(
        "spoot.office",
        string="Oficina",
        required=True,
    )

    partner_id = fields.Many2one(
        "res.partner",
        string="Cliente",
        required=True,
        help="Persona que realiza la reserva.",
    )

    date = fields.Date(
        string="Fecha de reserva",
        required=True,
    )

    slot_type = fields.Selection(
        [
            ("morning", "Mañana (8:00 - 12:00)"),
            ("afternoon", "Tarde (14:00 - 18:00)"),
            ("full_day", "Todo el día (8:00 - 18:00)"),
        ],
        string="Franja horaria",
        required=True,
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
    )

    paid = fields.Boolean(
        string="Pagado",
        help="Se marcará en verdadero cuando el pago esté realizado.",
    )

    start_datetime = fields.Datetime(
        string="Inicio",
        compute="_compute_datetimes",
        store=True,
    )
    end_datetime = fields.Datetime(
        string="Fin",
        compute="_compute_datetimes",
        store=True,
    )

    google_event_id = fields.Char(
        string="ID evento calendario (externo)",
        help="Se puede usar para sincronizar con Google Calendar u otros.",
    )

    notes = fields.Text(string="Notas internas")

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
            else:  # full_day
                start_t, end_t = time(8, 0), time(18, 0)

            rec.start_datetime = datetime.combine(rec.date, start_t)
            rec.end_datetime = datetime.combine(rec.date, end_t)

    @api.model
    def get_availability(self, office_id, date_str):
        """
        Retorna franjas disponibles para una oficina y fecha.
        date_str: 'YYYY-MM-DD'
        """
        if not office_id or not date_str:
            return {"available": [], "taken": []}

        # normaliza date
        date = fields.Date.from_string(date_str)

        taken = self.search([
            ("office_id", "=", int(office_id)),
            ("date", "=", date),
            ("state", "!=", "cancelled"),
        ]).mapped("slot_type")

        all_slots = ["morning", "afternoon", "full_day"]

        # Reglas: si full_day está tomado → nada disponible
        # si morning y afternoon están tomados → full_day tampoco
        taken_set = set(taken)
        available = []

        if "full_day" in taken_set:
            available = []
        else:
            # si está tomado morning o afternoon, igual puede existir el otro,
            # pero full_day solo si ambos libres.
            if "morning" not in taken_set:
                available.append("morning")
            if "afternoon" not in taken_set:
                available.append("afternoon")
            if ("morning" not in taken_set) and ("afternoon" not in taken_set):
                available.append("full_day")

        return {"available": available, "taken": list(taken_set)}
    @api.constrains("office_id", "start_datetime", "end_datetime", "state")
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
                if self.search_count(domain):
                    raise ValidationError(_("Esa franja ya está reservada. Elige otra."))

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
            # Formato: YYYYMMDDTHHMMSSZ (UTC)
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
