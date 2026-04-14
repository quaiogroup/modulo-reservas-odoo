# -*- coding: utf-8 -*-
from odoo import api, fields, models


class OfficeSettings(models.TransientModel):
    _name = "office.settings"
    _description = "Configuración de Office Booking"

    # ── Notificaciones ────────────────────────────────────────────────
    admin_email = fields.Char(
        string="Correo del administrador",
        help="Dirección que recibirá todas las notificaciones internas "
             "(nueva reserva, cancelación, etc.). "
             "Si se deja vacío se usa el correo de la empresa.",
    )

    # ── Accesos directos a plantillas ─────────────────────────────────
    # (solo para mostrar en la vista — los botones abren la plantilla)

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        param = self.env["ir.config_parameter"].sudo()
        res["admin_email"] = param.get_param(
            "office_booking.admin_email", ""
        )
        return res

    def action_save(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "office_booking.admin_email",
            (self.admin_email or "").strip(),
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Configuración guardada",
                "message": "Los cambios han sido aplicados.",
                "type": "success",
                "sticky": False,
            },
        }

    # ── Botones para abrir cada plantilla ─────────────────────────────
    def _open_template(self, xml_id):
        template = self.env.ref(xml_id, raise_if_not_found=False)
        if not template:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "mail.template",
            "view_mode": "form",
            "res_id": template.id,
            "target": "new",
        }

    def action_edit_tpl_booking_pending(self):
        return self._open_template("office_booking.mail_template_booking_pending_payment")

    def action_edit_tpl_booking_confirmed_plan(self):
        return self._open_template("office_booking.mail_template_booking_confirmed_plan")

    def action_edit_tpl_booking_confirmed_bold(self):
        return self._open_template("office_booking.mail_template_booking_confirmed_bold")

    def action_edit_tpl_booking_reminder(self):
        return self._open_template("office_booking.mail_template_booking_reminder")

    def action_edit_tpl_booking_cancelled_user(self):
        return self._open_template("office_booking.mail_template_booking_cancelled_user")

    def action_edit_tpl_booking_cancelled_admin(self):
        return self._open_template("office_booking.mail_template_booking_cancelled_admin")

    def action_edit_tpl_booking_new_admin(self):
        return self._open_template("office_booking.mail_template_booking_new_admin")
