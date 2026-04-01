{
    "name": "Spoot Office Booking",
    "summary": "Gestor de reservas de oficinas con website, portal y correos",
    "version": "19.0.1.0.0",
    "author": "SPPOT SAS",
    "website": "https://sppot.co",
    "license": "LGPL-3",
    "category": "Services/Booking",
    "depends": [
        "base",
        "contacts",
        "mail",
        "website",
        "portal",
        "calendar",
        "payment",  # preparado para pagos
    ],
'data': [
    'security/ir.model.access.csv',

    # DATOS (templates y crons) — antes de las vistas
    'data/mail_templates.xml',
    'data/ir_cron_data.xml',

    # VISTAS PRIMERO
    'views/office_views.xml',
    'views/booking_views.xml',
    'views/office_block_views.xml',
    'views/coworking_plan_views.xml',
    'views/coworking_subscription_views.xml',
    'views/availability_views.xml',
        'views/portal_templates.xml',
        'views/website_templates.xml',


    # MENÚS AL FINAL
    'views/menu_views.xml',
],

    "assets": {
        "web.assets_frontend": [
            "spoot_office_booking/static/src/css/custom.css",
            "spoot_office_booking/static/src/js/office_calendar.js",
            "spoot_office_booking/static/src/js/office_booking.js",
            "spoot_office_booking/static/src/js/coworking_calendar.js",
        ],
         "web.assets_backend": [
        "spoot_office_booking/static/src/js/availability_dashboard.js",
        "spoot_office_booking/static/src/xml/availability_dashboard.xml",
        "spoot_office_booking/static/src/css/admin_availability.css",
    ],
    },


    "installable": True,
    "application": True,
}
