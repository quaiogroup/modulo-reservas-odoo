odoo.define("spoot_office_booking.office_calendar", function (require) {
    "use strict";

    const publicWidget = require("web.public.widget");
    const rpc = require("web.rpc");

    publicWidget.registry.SpootOfficeCalendar = publicWidget.Widget.extend({
        selector: ".js_spoot_office_calendar",

        start: function () {
            this.officeId = this.$el.data("officeId");
            this.$calEl = this.$("#spootCalendar");

            if (!this.officeId || !this.$calEl.length) {
                return this._super.apply(this, arguments);
            }

            if (typeof FullCalendar === "undefined") {
                this.$calEl.html(
                    '<div class="alert alert-warning mb-0">' +
                    "FullCalendar no está cargando. Revisa assets_frontend." +
                    "</div>"
                );
                return this._super.apply(this, arguments);
            }

            const calendar = new FullCalendar.Calendar(this.$calEl[0], {
                initialView: "dayGridMonth",
                height: 460,
                firstDay: 1,
                locale: "es",
                headerToolbar: {
                    left: "prev,next today",
                    center: "title",
                    right: "dayGridMonth,timeGridWeek,timeGridDay",
                },
                events: (info, success, failure) => {
                    rpc.query({
                        route: "/spoot/calendar/events",
                        params: {
                            office_id: this.officeId,
                            start: info.startStr,
                            end: info.endStr,
                        },
                    }).then(success).catch(function (err) {
                        console.error(err);
                        failure(err);
                    });
                },
            });

            calendar.render();

            return this._super.apply(this, arguments);
        },
    });
});
