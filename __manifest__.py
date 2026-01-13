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
"data": [
    "security/ir.model.access.csv",
    "views/office_views.xml",
    "views/booking_views.xml",
    "views/menu_views.xml",
    "views/website_templates.xml",
    "views/portal_templates.xml",

    # "data/mail_templates.xml",  # lo quitamos por ahora
],
    "assets": {
        "web.assets_frontend": [
            "spoot_office_booking/static/src/css/custom.css",
                    "spoot_office_booking/static/src/js/office_calendar.js",
                            "spoot_office_booking/static/src/js/office_booking.js",


        ],
    },


    "installable": True,
    "application": True,
}
