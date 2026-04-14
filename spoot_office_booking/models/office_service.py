from odoo import models, fields, api

class SpootOfficeService(models.Model):
    _name = "spoot.office.service"
    _description = "Servicio de oficina"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    # Para “defaults”
    is_default = fields.Boolean(string="Servicio por defecto", default=False)

    # Para mostrar bonito en web — solo íconos FA4 (los que incluye Odoo)
    icon = fields.Selection([
        ("fa-wifi",          "WiFi"),
        ("fa-coffee",        "Café / Bebidas"),
        ("fa-print",         "Impresora"),
        ("fa-desktop",       "Computador"),
        ("fa-television",    "Pantalla / TV"),
        ("fa-video-camera",  "Videoconferencia"),
        ("fa-phone",         "Teléfono"),
        ("fa-users",         "Sala de reuniones"),
        ("fa-car",           "Parqueadero"),
        ("fa-snowflake-o",   "Aire acondicionado"),
        ("fa-lock",          "Casillero / Seguridad"),
        ("fa-cutlery",       "Cocina / Comedor"),
        ("fa-bolt",          "Cargadores"),
        ("fa-music",         "Zona de descanso"),
        ("fa-building",      "Recepción"),
        ("fa-clock-o",       "Acceso 24/7"),
        ("fa-shower",        "Ducha"),
        ("fa-wheelchair",    "Acceso accesible"),
    ], string="Icono")
    description = fields.Char(string="Descripción corta")


class SpootOffice(models.Model):
    _inherit = "spoot.office"

    service_ids = fields.Many2many(
        "spoot.office.service",
        "spoot_office_service_rel",
        "office_id",
        "service_id",
        string="Servicios",
        domain=[("active", "=", True)],
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "service_ids" in fields_list:
            defaults = self.env["spoot.office.service"].search([
                ("is_default", "=", True),
                ("active", "=", True),
            ])
            res["service_ids"] = [(6, 0, defaults.ids)]
        return res
