/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

function label(slot) {
  if (slot === "morning") return "Mañana (8-12)";
  if (slot === "afternoon") return "Tarde (14-18)";
  return "Todo el día";
}

async function refreshAvailability(officeId, day) {
  const data = await rpc("/spoot/office/availability", { office_id: officeId, day });
  if (data.error) return;

  const select = document.getElementById("spoot_slot");
  const hint = document.getElementById("spoot_slot_hint");
  const available = new Set(data.available);

  // Recorre opciones y deshabilita según disponibilidad
  Array.from(select.options).forEach(opt => {
    if (!opt.value) return;
    opt.disabled = !available.has(opt.value);
  });

  // Si la opción elegida quedó inválida, resetea
  if (select.value && !available.has(select.value)) {
    select.value = "";
  }

  // Mensaje al usuario
  const taken = data.taken || [];
  if (!taken.length) {
    hint.textContent = "✅ Todas las franjas están disponibles.";
  } else {
    hint.textContent = `⛔ Ocupadas: ${taken.map(label).join(", ")}`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const calendarWrap = document.querySelector(".js_spoot_office_calendar");
  const officeId = calendarWrap?.dataset?.officeId;
  const dateInput = document.getElementById("spoot_date");

  if (!officeId || !dateInput) return;

  // Cuando el usuario cambia la fecha
  dateInput.addEventListener("change", () => {
    if (!dateInput.value) return;
    refreshAvailability(officeId, dateInput.value);
  });

  // Opcional: si ya viene una fecha puesta
  if (dateInput.value) {
    refreshAvailability(officeId, dateInput.value);
  }
});
