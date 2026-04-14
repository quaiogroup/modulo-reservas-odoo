import uuid
from datetime import timedelta

from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class SpootCoworkingSubscription(models.Model):
    _name = "spoot.coworking.subscription"
    _description = "Suscripción activa de coworking"
    _order = "end_date desc"

    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="cascade",
    )

    plan_id = fields.Many2one(
        "spoot.coworking.plan",
        required=True,
    )

    start_date = fields.Date(
        required=True,
        default=fields.Date.today,
    )

    end_date = fields.Date(required=True)

    # Float to support half-day increments (morning/afternoon = 0.5, full_day = 1.0)
    total_days = fields.Float(required=True, digits=(6, 1))
    remaining_days = fields.Float(required=True, digits=(6, 1))

    state = fields.Selection(
        [
            ("pending_payment", "Pendiente de pago"),
            ("active", "Activa"),
            ("expired", "Vencida"),
            ("cancelled", "Cancelada"),
        ],
        default="pending_payment",
    )

    # ── Bold payment fields ────────────────────────────────────────────────
    bold_order_id = fields.Char(
        string="Bold Order ID",
        copy=False,
        readonly=True,
        index=True,
    )
    bold_tx_id = fields.Char(
        string="Bold Transaction ID",
        copy=False,
        readonly=True,
    )
    bold_payment_status = fields.Char(
        string="Bold Payment Status",
        copy=False,
        readonly=True,
    )

    # ── Email notification helpers ─────────────────────────────────────────

    def _notify_customer(self, template_xml_id):
        """Send a transactional email to the subscription's partner."""
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
                _logger.info("[NOTIFY] customer email sent — template=%s sub=%s", template_xml_id, self.id)
            else:
                _logger.warning("[NOTIFY] template not found: %s", template_xml_id)
        except Exception as exc:
            _logger.error("[NOTIFY] customer email FAILED — template=%s sub=%s error=%s",
                          template_xml_id, self.id, exc)

    def _notify_admin(self, template_xml_id):
        """Send a notification email to the configured administrator address."""
        self.ensure_one()
        param = self.env["ir.config_parameter"].sudo()
        admin_email = (
            param.get_param("spoot_office_booking.admin_email")
            or self.env.company.email
            or ""
        )
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
                _logger.info("[NOTIFY] admin email sent — template=%s sub=%s to=%s",
                             template_xml_id, self.id, admin_email)
            else:
                _logger.warning("[NOTIFY] template not found: %s", template_xml_id)
        except Exception as exc:
            _logger.error("[NOTIFY] admin email FAILED — template=%s sub=%s error=%s",
                          template_xml_id, self.id, exc)

    # ── Bold helpers ───────────────────────────────────────────────────────

    def _ensure_bold_order_id(self):
        """Return existing Bold order ID or generate a new one."""
        self.ensure_one()
        if not self.bold_order_id:
            self.sudo().write({
                "bold_order_id": f"SPPOT-PLAN-{self.id}-{uuid.uuid4().hex[:10]}"
            })
        return self.bold_order_id

    def action_mark_paid(self, tx_id=None):
        """
        Activate the subscription after successful Bold payment.
        Idempotent: already-active subscriptions are skipped.
        Also guards against activating a second plan while another is already active.
        """
        for rec in self:
            if rec.state in ("active", "expired"):
                _logger.info(
                    "[BOLD PLAN] action_mark_paid skipped — already %s (subscription id=%s)",
                    rec.state, rec.id,
                )
                continue

            # ── Model-level safety gate ────────────────────────────────
            # If the partner somehow already has an active subscription (e.g. via
            # a concurrent request or webhook), do NOT create a duplicate.
            existing_active = self.sudo().search([
                ("partner_id", "=", rec.partner_id.id),
                ("state", "=", "active"),
                ("id", "!=", rec.id),
            ], limit=1)
            if existing_active:
                _logger.warning(
                    "[BOLD PLAN] action_mark_paid BLOCKED — partner %s already has "
                    "active subscription %s; will not activate subscription %s.",
                    rec.partner_id.id, existing_active.id, rec.id,
                )
                continue

            start = fields.Date.today()
            end = start + timedelta(days=rec.plan_id.validity_days)

            rec.write({
                "state": "active",
                "start_date": start,
                "end_date": end,
                "total_days": rec.plan_id.days_included,
                "remaining_days": rec.plan_id.days_included,
                "bold_tx_id": tx_id or rec.bold_tx_id,
                "bold_payment_status": "APPROVED",
            })

            _logger.info(
                "[BOLD PLAN] subscription id=%s activated for partner=%s plan=%s "
                "start=%s end=%s days=%s",
                rec.id, rec.partner_id.id, rec.plan_id.name,
                start, end, rec.plan_id.days_included,
            )

            # Notify customer and admin of plan activation
            rec._notify_customer("spoot_office_booking.mail_template_plan_confirmed_user")
            rec._notify_admin("spoot_office_booking.mail_template_plan_confirmed_admin")

    # ── Legacy helpers (kept for backward compat) ─────────────────────────

    def consume_slot(self, slot_type):
        """Consume plan balance for a given slot type.
        slot_type: 'morning' | 'afternoon' → 0.5 days
                   'full_day'              → 1.0 day
        Returns True if successful, False if insufficient balance.
        """
        self.ensure_one()
        cost = 1.0 if slot_type == "full_day" else 0.5
        if self.remaining_days < cost:
            return False
        self.sudo().write({"remaining_days": self.remaining_days - cost})
        return True

    def consume_day(self):
        """Legacy helper — kept for backward compatibility."""
        self.ensure_one()
        if self.remaining_days < 1.0:
            return False
        self.sudo().write({"remaining_days": self.remaining_days - 1.0})
        return True

    def create_from_plan(self, partner, plan):
        """Create an already-active subscription (used without payment flow)."""
        start = fields.Date.today()
        end = start + timedelta(days=plan.validity_days)

        return self.create({
            "partner_id": partner.id,
            "plan_id": plan.id,
            "start_date": start,
            "end_date": end,
            "total_days": plan.days_included,
            "remaining_days": plan.days_included,
            "state": "active",
        })
