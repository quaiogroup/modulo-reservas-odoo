"""Rename all `spoot_*` DB artifacts to `sppot_*` (brand typo fix).

Runs automatically on `odoo -u office_booking` when the module version bumps to
19.0.1.1.0 — in local AND production, no manual SQL needed. Idempotent.

Odoo runs pre-migration BEFORE loading the new field definitions, so the columns
are renamed first and the ORM finds the existing data under the new names
(no empty columns, no data loss).
"""
import logging

_logger = logging.getLogger(__name__)

# Only STORED columns on res_partner need renaming (One2many / non-stored
# computed fields have no column).
COLUMN_RENAMES = [
    ("spoot_document_type", "sppot_document_type"),
    ("spoot_document_number", "sppot_document_number"),
    ("spoot_billing_name", "sppot_billing_name"),
    ("spoot_booking_count", "sppot_booking_count"),
]


def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    # 1) Rename real columns on res_partner, preserving data. -----------------
    for old, new in COLUMN_RENAMES:
        if _column_exists(cr, "res_partner", old) and not _column_exists(
            cr, "res_partner", new
        ):
            cr.execute(
                'ALTER TABLE res_partner RENAME COLUMN "%s" TO "%s"' % (old, new)
            )
            _logger.info("[spoot->sppot] renamed column res_partner.%s -> %s", old, new)

    # 2) Fix external IDs in ir_model_data so records (services, views, actions,
    #    menus, field metadata) keep their identity instead of being duplicated
    #    or orphaned on load. Covers 'spoot' anywhere in the name. ------------
    cr.execute(
        """
        UPDATE ir_model_data
        SET name = regexp_replace(name, 'spoot', 'sppot', 'g')
        WHERE module = 'office_booking' AND name LIKE '%spoot%'
        """
    )
    _logger.info("[spoot->sppot] updated %s ir_model_data external IDs", cr.rowcount)

    # 3) Rewrite COW / custom views (website-editor copies + Studio views).
    #    The module reload does NOT touch these detached views, so their arch_db
    #    still references old classes/fields/routes — fix them in place. The
    #    regexp only touches the 'spoot' substring, so the jsonb stays valid.
    cr.execute(
        r"""
        UPDATE ir_ui_view
        SET arch_db = regexp_replace(
                        regexp_replace(
                          regexp_replace(arch_db::text, 'SPOOT', 'SPPOT', 'g'),
                          'Spoot', 'Sppot', 'g'),
                        'spoot', 'sppot', 'g')::jsonb
        WHERE arch_db::text ~ 'spoot|Spoot|SPOOT'
        """
    )
    _logger.info("[spoot->sppot] rewrote %s custom/COW views", cr.rowcount)

    # 4) Fix window-action domains/contexts that filter on renamed fields
    #    (e.g. the Customers action domain [('spoot_booking_count','>',0)]).
    cr.execute(
        r"""
        UPDATE ir_act_window
        SET domain  = regexp_replace(regexp_replace(regexp_replace(
                          COALESCE(domain, ''),  'SPOOT', 'SPPOT', 'g'), 'Spoot', 'Sppot', 'g'), 'spoot', 'sppot', 'g'),
            context = regexp_replace(regexp_replace(regexp_replace(
                          COALESCE(context, ''), 'SPOOT', 'SPPOT', 'g'), 'Spoot', 'Sppot', 'g'), 'spoot', 'sppot', 'g')
        WHERE (COALESCE(domain, '') || COALESCE(context, '')) ~ 'spoot|Spoot|SPOOT'
        """
    )
    _logger.info("[spoot->sppot] fixed %s window actions", cr.rowcount)
