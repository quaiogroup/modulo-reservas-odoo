/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

console.log("SPPOT dashboard loaded ✅");

class SpootAvailabilityDashboard extends Component {
  setup() {
    this.orm = useService("orm");
    this.actionService = useService("action");
    this.setMode = this.setMode.bind(this);
this.shift = this.shift.bind(this);
this.onSegmentClick = this.onSegmentClick.bind(this);
this.goToday = this.goToday.bind(this);



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
      monthLabel: "",
monthWeeks: [], // array de semanas, cada semana array de 7 celdas {date, day, dow, isInMonth}

    });

    onWillStart(async () => {
      await this.load();
    });
  }

  _toISODate(d) {
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  }
  _fromISODate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d); // LOCAL ✅
}


async load() {
  this.state.loading = true;

  const res = await this.orm.call(
    "spoot.office.booking",
    "get_admin_availability_matrix",
    [this.state.dateStart, this.state.dateEnd, null]
  );

  // days -> objetos {date, day, dow}
  const days = (res.days || []).map((dateStr) => {
    const [y, m, d] = dateStr.split("-").map(Number);
    const dateObj = new Date(y, m - 1, d);
    return {
      date: dateStr,
      day: d,
      dow: dateObj.toLocaleDateString("es-CO", { weekday: "short" }),
    };
  });

  // rows -> asegurar days_by_date SIEMPRE
  const rows = (res.rows || []).map((row) => {
    const days_by_date = {};
    (row.days || []).forEach((cell) => {
      days_by_date[cell.date] = cell;
    });
    return { ...row, days_by_date };
  });

  this.state.data = { ...res, days, rows };

  // Label del mes
  const baseStart = new Date(this.state.dateStart.split("-").map(Number)[0],
                             this.state.dateStart.split("-").map(Number)[1] - 1,
                             this.state.dateStart.split("-").map(Number)[2]);
  this.state.monthLabel = baseStart.toLocaleDateString("es-CO", {
    month: "long",
    year: "numeric",
  });

  // Grid del mes (solo en modo month)
  if (this.state.mode === "month") {
    const firstOfMonth = new Date(baseStart.getFullYear(), baseStart.getMonth(), 1);
    const lastOfMonth = new Date(baseStart.getFullYear(), baseStart.getMonth() + 1, 0);

    // empezar lunes
    const firstDow = firstOfMonth.getDay(); // 0..6
    const diffToMonday = (firstDow === 0 ? -6 : 1) - firstDow;
    const gridStart = new Date(firstOfMonth);
    gridStart.setDate(firstOfMonth.getDate() + diffToMonday);

    // terminar domingo
    const lastDow = lastOfMonth.getDay();
    const diffToSunday = (lastDow === 0 ? 0 : 7 - lastDow);
    const gridEnd = new Date(lastOfMonth);
    gridEnd.setDate(lastOfMonth.getDate() + diffToSunday);

    const weeks = [];
    let cursor = new Date(gridStart);

    while (cursor <= gridEnd) {
      const week = [];
      for (let i = 0; i < 7; i++) {
        const y = cursor.getFullYear();
        const m = cursor.getMonth() + 1;
        const d = cursor.getDate();
        const dateStr = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;

        week.push({
          date: dateStr,
          day: d,
          isInMonth: cursor.getMonth() === baseStart.getMonth(),
        });

        cursor.setDate(cursor.getDate() + 1);
      }
      weeks.push(week);
    }

    this.state.monthWeeks = weeks;
  } else {
    this.state.monthWeeks = [];
  }

  this.state.loading = false;
}




  async setMode(mode) {
    this.state.mode = mode;

const base = this._fromISODate(this.state.dateStart);

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

  async goToday() {
  const today = new Date();
  const iso = this._toISODate(today);

  if (this.state.mode === "day") {
    this.state.dateStart = iso;
    this.state.dateEnd = iso;
  }

  if (this.state.mode === "week") {
    const monday = new Date(today);
    const day = monday.getDay();
    const diff = (day === 0 ? -6 : 1) - day;
    monday.setDate(monday.getDate() + diff);

    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);

    this.state.dateStart = this._toISODate(monday);
    this.state.dateEnd = this._toISODate(sunday);
  }

  if (this.state.mode === "month") {
    const first = new Date(today.getFullYear(), today.getMonth(), 1);
    const last = new Date(today.getFullYear(), today.getMonth() + 1, 0);
    this.state.dateStart = this._toISODate(first);
    this.state.dateEnd = this._toISODate(last);
  }

  await this.load();
}


async shift(step) {
  let start = this._fromISODate(this.state.dateStart);
  let end = this._fromISODate(this.state.dateEnd);

  if (this.state.mode === "day") {
    start.setDate(start.getDate() + step);
    end.setDate(end.getDate() + step);
    this.state.dateStart = this._toISODate(start);
    this.state.dateEnd = this._toISODate(end);
  } else if (this.state.mode === "week") {
    start.setDate(start.getDate() + 7 * step);
    end.setDate(end.getDate() + 7 * step);
    this.state.dateStart = this._toISODate(start);
    this.state.dateEnd = this._toISODate(end);
  } else if (this.state.mode === "month") {
    const base = this._fromISODate(this.state.dateStart);
    const first = new Date(base.getFullYear(), base.getMonth() + step, 1);
    const last = new Date(base.getFullYear(), base.getMonth() + step + 1, 0);
    this.state.dateStart = this._toISODate(first);
    this.state.dateEnd = this._toISODate(last);
  }

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

SpootAvailabilityDashboard.template =
  "spoot_office_booking.SpootAvailabilityDashboard";

// OJO: esta key debe coincidir con <field name="tag"> en tu ir.actions.client
registry
  .category("actions")
  .add("spoot_office_booking.availability_dashboard", SpootAvailabilityDashboard);
