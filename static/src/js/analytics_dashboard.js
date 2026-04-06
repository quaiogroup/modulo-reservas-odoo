/** @odoo-module **/
import { registry }    from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService }  from "@web/core/utils/hooks";

class SpootAnalyticsDashboard extends Component {
  setup() {
    this.orm           = useService("orm");
    this.actionService = useService("action");
    this.state = useState({
      data: null,
      loading: true,
      showExport: false,
      exportFrom: "",
      exportTo: "",
      exportState: "all",
    });
    onWillStart(async () => { await this.load(); });
  }

  async load() {
    this.state.loading = true;
    const data = await this.orm.call(
      "spoot.office.booking", "get_analytics_data", []
    );
    this.state.data = data;
    this.state.loading = false;
  }

  /* ── bar chart helpers ──────────────────────────────────────────── */
  barMax(key) {
    if (!this.state.data) return 1;
    return Math.max(...this.state.data.monthly.map(m => m[key])) || 1;
  }

  barPct(value, key) {
    return Math.round((value / this.barMax(key)) * 100);
  }

  /* ── diff badge ─────────────────────────────────────────────────── */
  diff(current, prev) {
    if (!prev) return { label: "—", cls: "" };
    const d = current - prev;
    const pct = Math.round(Math.abs(d) / prev * 100);
    return {
      label: (d >= 0 ? "▲ " : "▼ ") + pct + "%",
      cls:   d >= 0 ? "an-diff--up" : "an-diff--down",
    };
  }

  /* ── format money ───────────────────────────────────────────────── */
  fmtMoney(n) {
    const sym = this.state.data?.currency || "$";
    return sym + " " + Math.round(n || 0).toLocaleString("es-CO");
  }

  /* ── export ─────────────────────────────────────────────────────── */
  exportCsv() {
    this.state.showExport = !this.state.showExport;
  }

  exportUrl() {
    const p = new URLSearchParams();
    if (this.state.exportFrom)  p.set("date_from", this.state.exportFrom);
    if (this.state.exportTo)    p.set("date_to",   this.state.exportTo);
    if (this.state.exportState) p.set("state",     this.state.exportState);
    return "/spoot/export/bookings?" + p.toString();
  }

  /* ── open bookings list ─────────────────────────────────────────── */
  openBookings() {
    this.actionService.doAction({
      type: "ir.actions.act_window",
      name: "Reservas",
      res_model: "spoot.office.booking",
      views: [[false, "list"], [false, "form"]],
      target: "current",
    });
  }

  /* ── open client form ───────────────────────────────────────────── */
  openClient(partnerId) {
    this.actionService.doAction({
      type: "ir.actions.act_window",
      name: "Cliente",
      res_model: "res.partner",
      res_id: partnerId,
      views: [[false, "form"]],
      target: "current",
      context: { form_view_ref: "spoot_office_booking.view_spoot_client_form" },
    });
  }
}

SpootAnalyticsDashboard.template =
  "spoot_office_booking.SpootAnalyticsDashboard";

registry
  .category("actions")
  .add("spoot_office_booking.analytics_dashboard", SpootAnalyticsDashboard);
