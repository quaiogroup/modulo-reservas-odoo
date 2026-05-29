# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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

    # ── Diagnóstico de email ───────────────────────────────────────────
    def action_diagnose_email(self):
        """Verifica la configuración de email y devuelve un resumen."""
        param = self.env["ir.config_parameter"].sudo()
        smtp_servers = self.env["ir.mail_server"].sudo().search([])
        company = self.env.company
        admin_email = (self.admin_email or "").strip() or param.get_param("office_booking.admin_email", "")

        lines = []
        ok = True

        if smtp_servers:
            names = ", ".join(s.name for s in smtp_servers[:3])
            lines.append(f"✅ Servidor SMTP: {names}")
        else:
            lines.append("⚠️ No hay servidor SMTP configurado (se usará el servidor de Odoo por defecto).")
            ok = False

        if company.email:
            lines.append(f"✅ Correo de empresa: {company.email}")
        else:
            lines.append("❌ El correo de la empresa está vacío. Los correos pueden no enviarse.")
            ok = False

        if admin_email:
            lines.append(f"✅ Correo admin (notificaciones): {admin_email}")
        else:
            lines.append(f"⚠️ Correo admin no configurado — se usará: {company.email or '(vacío)'}")

        failed = self.env["mail.mail"].sudo().search_count([("state", "=", "exception")])
        if failed:
            lines.append(f"⚠️ Hay {failed} correo(s) en estado de error (envío fallido).")
        else:
            lines.append("✅ Sin correos en cola de error.")

        msg = "\n".join(lines)
        _logger.info("[EMAIL DIAG] %s", msg)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Diagnóstico de correo electrónico",
                "message": msg,
                "type": "success" if ok else "warning",
                "sticky": True,
            },
        }

    def action_send_test_email(self):
        """Envía un correo de prueba al correo admin configurado."""
        param = self.env["ir.config_parameter"].sudo()
        dest = (self.admin_email or "").strip() or param.get_param("office_booking.admin_email", "")
        if not dest:
            dest = self.env.company.email
        if not dest:
            raise UserError(
                "No hay correo de destino. Configura el correo del administrador o el correo de la empresa."
            )

        from_email = self.env.company.email or dest
        base_url = param.get_param("web.base.url", "http://localhost:8069")

        mail = self.env["mail.mail"].sudo().create({
            "subject": "[PRUEBA] Correo de prueba – Office Booking",
            "body_html": f"""
<div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;
            border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
  <div style="background:#1e293b;padding:24px;text-align:center;">
    <h2 style="color:#fff;margin:0;">Correo de prueba</h2>
  </div>
  <div style="padding:28px;">
    <p style="font-size:15px;color:#374151;">
      Este es un <strong>correo de prueba</strong> del sistema <strong>Office Booking</strong>.
    </p>
    <p style="font-size:14px;color:#6b7280;">
      Si lo recibiste correctamente, el servidor de correo está funcionando bien.
    </p>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;"/>
    <p style="font-size:12px;color:#9ca3af;">
      Sistema: {self.env.company.name}<br/>
      URL: {base_url}<br/>
      Enviado desde: {from_email}
    </p>
  </div>
</div>""",
            "email_to": dest,
            "email_from": from_email,
            "auto_delete": False,
        })

        try:
            mail.sudo().send(raise_exception=True)
            _logger.info("[EMAIL TEST] Test email sent to %s", dest)
            msg_type = "success"
            msg = f"Correo enviado a {dest}. Revisa tu bandeja de entrada (y la carpeta de spam)."
        except Exception as exc:
            _logger.error("[EMAIL TEST] Failed to send test email: %s", exc)
            msg_type = "danger"
            msg = f"Error al enviar el correo: {exc}\n\nRevisa la configuración del servidor SMTP."

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Correo de prueba",
                "message": msg,
                "type": msg_type,
                "sticky": True,
            },
        }

    def action_view_failed_emails(self):
        """Abre la lista de correos que fallaron (estado exception)."""
        return {
            "type": "ir.actions.act_window",
            "name": "Correos fallidos",
            "res_model": "mail.mail",
            "view_mode": "list,form",
            "domain": [("state", "=", "exception")],
            "context": {"search_default_state_exception": 1},
        }

    def action_view_smtp_settings(self):
        """Abre la configuración de servidores de correo saliente."""
        return {
            "type": "ir.actions.act_window",
            "name": "Servidores de correo saliente",
            "res_model": "ir.mail_server",
            "view_mode": "list,form",
            "target": "current",
        }

    def action_view_all_sent_emails(self):
        """Abre todos los correos de reservas (incluye fallidos)."""
        return {
            "type": "ir.actions.act_window",
            "name": "Correos de reservas",
            "res_model": "mail.message",
            "view_mode": "list,form",
            "domain": [
                ("model", "in", ["office.booking", "office.subscription"]),
                ("message_type", "in", ["email", "auto_email"]),
            ],
            "context": {"default_message_type": "email"},
        }
