/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

console.log("SPPOT dashboard loaded ✅");
class SpootAvailabilityDashboard extends Component {
  setup() {
    this.orm = useService("orm");
this.actionService = useService("action");

    const today = new Date();
    const start = new Date(today);
    start.setDate(today.getDate() - today.getDay() + 1); // lunes (aprox)
    const end = new Date(start);
    end.setDate(start.getDate() + 6); // domingo
    console.log("actionService:", this.actionService);


    this.state = useState({
      mode: "week", // day | week | month
      dateStart: this._toISODate(start),
      dateEnd: this._toISODate(end),
      data: null,
      loading: true,
    });

    onWillStart(async () => {
      await this.load();
    });
  }

  _toISODate(d) {
    // YYYY-MM-DD en local
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  }

  async load() {
    this.state.loading = true;
    this.state.data = await this.orm.call(
      "spoot.office.booking",
      "get_admin_availability_matrix",
      [this.state.dateStart, this.state.dateEnd, null]
    );
    this.state.loading = false;
  }

  async setMode(mode) {
    this.state.mode = mode;

    const base = new Date(this.state.dateStart);
    if (mode === "day") {
      this.state.dateEnd = this.state.dateStart;
    } else if (mode === "week") {
      const monday = new Date(base);
      const day = monday.getDay();
      const diff = (day === 0 ? -6 : 1) - day;
      monday.setDate(monday.getDate() + diff);
      const sunday = new Date(monday);
      sunday.setDate(monday.getDate() + 6);
      this.state.dateStart = this._toISODate(monday);
      this.state.dateEnd = this._toISODate(sunday);
    } else if (mode === "month") {
      const first = new Date(base.getFullYear(), base.getMonth(), 1);
      const last = new Date(base.getFullYear(), base.getMonth() + 1, 0);
      this.state.dateStart = this._toISODate(first);
      this.state.dateEnd = this._toISODate(last);
    }

    await this.load();
  }

  async shift(deltaDays) {
    const s = new Date(this.state.dateStart);
    const e = new Date(this.state.dateEnd);

    s.setDate(s.getDate() + deltaDays);
    e.setDate(e.getDate() + deltaDays);

    this.state.dateStart = this._toISODate(s);
    this.state.dateEnd = this._toISODate(e);
    await this.load();
  }

  // Click en segmento: si hay booking_id abre form, si no abre wizard
  async onSegmentClick(officeId, dateStr, slotType, seg) {
    if (seg.booking_id) {
await this.actionService.doAction({
  type: "ir.actions.act_window",
  name: "Reserva",
  res_model: "spoot.office.booking",
  res_id: seg.booking_id,
  views: [[false, "form"]],
  target: "current",
});

      return;
    }

    // Crear wizard (reserva rápida)
await this.actionService.doAction({
  type: "ir.actions.act_window",
  name: "Crear reserva",
  res_model: "spoot.booking.quick.create.wizard",
  views: [[false, "form"]],
  target: "new",
  context: {
    default_office_id: officeId,
    default_date: dateStr,
    default_slot_type: slotType,
  },
});

  }

  // Helpers de clase CSS por estado
  segClass(status) {
    if (status === "busy") return "spoot-pill-busy";
    if (status === "pending") return "spoot-pill-pending";
    return "spoot-pill-free";
  }
}

SpootAvailabilityDashboard.template = "spoot_office_booking.SpootAvailabilityDashboard";

registry.category("actions").add("spoot_office_booking.availability_dashboard", SpootAvailabilityDashboard);
