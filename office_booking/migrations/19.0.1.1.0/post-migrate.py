"""Post-load cleanup for the spoot -> sppot rename.

After the module loads, Odoo has created the new `sppot_*` field definitions and
re-linked their external IDs. The old `spoot_*` field metadata on res.partner /
res.users (res.users mirrors partner fields by delegation) is now orphaned — its
column was already renamed and no Python field defines it. Remove the leftovers.
Idempotent: a second run simply deletes nothing.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        DELETE FROM ir_model_fields
        WHERE name LIKE 'spoot%' AND model IN ('res.partner', 'res.users')
        """
    )
    _logger.info(
        "[spoot->sppot] removed %s orphan spoot_* field definitions", cr.rowcount
    )
