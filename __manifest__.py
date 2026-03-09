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

    # 1) Vistas/acciones primero (aquí se crean los XML IDs)
    "views/office_views.xml",
    "views/booking_views.xml",
    "views/availability_views.xml", 
    # <-- si lo tienes, ponlo aquí
    "data/office_services_data.xml",

    # 2) Menús al final (porque referencian acciones ya creadas)
    "views/menu_views.xml",

    # 3) Plantillas web/portal (no suelen ser problema, pero ok aquí)
    "views/portal_templates.xml",
    "views/website_templates.xml",

    # 4) Wizards
    "wizards/booking_quick_create_wizard_views.xml",
],

    "assets": {
        "web.assets_frontend": [
            "spoot_office_booking/static/src/css/custom.css",
                    "spoot_office_booking/static/src/js/office_calendar.js",
                            "spoot_office_booking/static/src/js/office_booking.js",


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
