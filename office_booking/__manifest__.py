{
    "name": "Office Booking",
    "summary": "Complete office & coworking space booking system with website, portal, payments and email notifications",
    "description": "See static/description/index.html",
    "version": "19.0.1.0.0",
    "author": "Office Booking",
    "website": "",
    "license": "LGPL-3",
    "category": "Services/Booking",
    "images": ["static/description/banner.png"],
    "depends": [
        "base",
        "contacts",
        "mail",
        "website",
        "portal",
        "calendar",
    ],
    # All data loaded in post_init_hook so models are registered first
    "data": [],

    "assets": {
        "web.assets_frontend": [
            "office_booking/static/src/css/custom.css",
            "office_booking/static/src/js/office_calendar.js",
            "office_booking/static/src/js/office_booking.js",
            "office_booking/static/src/js/coworking_calendar.js",
        ],
        "web.assets_backend": [
            "office_booking/static/src/js/availability_dashboard.js",
            "office_booking/static/src/xml/availability_dashboard.xml",
            "office_booking/static/src/css/admin_availability.css",
            "office_booking/static/src/js/analytics_dashboard.js",
            "office_booking/static/src/xml/analytics_dashboard.xml",
            "office_booking/static/src/css/analytics_dashboard.css",
        ],
    },

    "installable": True,
    "application": True,
    "post_init_hook": "post_init_hook",
}
