from odoo import models, fields
from datetime import timedelta


class SpootCoworkingSubscription(models.Model):
    _name = "spoot.coworking.subscription"
    _description = "Suscripción activa de coworking"
    _order = "end_date desc"

    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="cascade"
    )

    plan_id = fields.Many2one(
        "spoot.coworking.plan",
        required=True
    )

    start_date = fields.Date(
        required=True,
        default=fields.Date.today
    )

    end_date = fields.Date(required=True)

    total_days = fields.Integer(required=True)
    remaining_days = fields.Integer(required=True)

    state = fields.Selection(
        [
            ("active", "Activa"),
            ("expired", "Vencida"),
        ],
        default="active",
    )

    def consume_day(self):
        for rec in self:
            if rec.remaining_days <= 0:
                return False
            rec.remaining_days -= 1
            return True

    def create_from_plan(self, partner, plan):
        start = fields.Date.today()
        end = start + timedelta(days=plan.validity_days)

        return self.create({
            "partner_id": partner.id,
            "plan_id": plan.id,
            "start_date": start,
            "end_date": end,
            "total_days": plan.days_included,
            "remaining_days": plan.days_included,
        })