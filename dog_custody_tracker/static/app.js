const state = {
  currentMonth: todayMonthKey(),
  today: null,
  participants: [],
  entries: [],
  totals: {},
  activeDate: null,
  calendar: null,
  suppressCalendarFetch: false,
};

const monthLabel = document.getElementById("monthLabel");
const totalsGrid = document.getElementById("totalsGrid");
const leadCopy = document.getElementById("leadCopy");
const participantButtons = document.getElementById("participantButtons");
const dayDialog = document.getElementById("dayDialog");
const dialogDateLabel = document.getElementById("dialogDateLabel");
const dialogStatus = document.getElementById("dialogStatus");
const importResult = document.getElementById("importResult");
const bulkPlanStatus = document.getElementById("bulkPlanStatus");
const bulkParticipant = document.getElementById("bulkParticipant");

document.getElementById("todayButton").addEventListener("click", () => {
  const monthKey = todayMonthKey();
  state.currentMonth = monthKey;
  state.suppressCalendarFetch = true;
  state.calendar.gotoDate(`${monthKey}-01`);
  loadMonth(monthKey);
});
document.getElementById("clearEntryButton").addEventListener("click", clearSelectedDay);
document.getElementById("bulkPlanForm").addEventListener("submit", submitBulkPlan);
document.getElementById("importForm").addEventListener("submit", submitImport);
document.getElementById("sheetImportButton").addEventListener("click", submitSheetImport);

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
}

initializeCalendar();
loadMonth(state.currentMonth);

function initializeCalendar() {
  const calendarEl = document.getElementById("calendar");
  state.calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: "dayGridMonth",
    firstDay: 1,
    height: "auto",
    initialDate: `${state.currentMonth}-01`,
    headerToolbar: {
      left: "prev,next today",
      center: "title",
      right: "",
    },
    buttonText: {
      today: "Today",
    },
    dateClick: (info) => openDayDialog(info.dateStr),
    eventClick: (info) => {
      openDayDialog(info.event.startStr.slice(0, 10));
    },
    datesSet: (info) => {
      const currentStart = info.view.currentStart;
      const monthKey = `${currentStart.getFullYear()}-${String(currentStart.getMonth() + 1).padStart(2, "0")}`;
      renderMonthLabel(monthKey);
      if (state.suppressCalendarFetch) {
        state.suppressCalendarFetch = false;
        return;
      }
      if (monthKey !== state.currentMonth) {
        state.currentMonth = monthKey;
        loadMonth(monthKey);
      }
    },
    eventContent: (arg) => {
      const wrapper = document.createElement("div");
      wrapper.className = "fc-event-card";
      const title = document.createElement("strong");
      title.textContent = arg.event.title;
      const meta = document.createElement("span");
      meta.textContent = arg.event.extendedProps.sourceLabel;
      wrapper.appendChild(title);
      wrapper.appendChild(meta);
      return { domNodes: [wrapper] };
    },
  });
  state.calendar.render();
}

async function loadMonth(monthKey = state.currentMonth) {
  const response = await fetch(`/api/bootstrap?month=${monthKey}`);
  const payload = await response.json();
  state.currentMonth = payload.month;
  state.today = payload.today;
  state.participants = payload.participants;
  state.entries = payload.entries;
  state.totals = payload.totals;
  render(payload);
}

function render(payload) {
  renderMonthLabel(payload.month);
  renderTotals(payload);
  renderBulkParticipantOptions();
  renderParticipantDialogButtons();
  renderCalendarEvents(payload.entries);
}

function renderMonthLabel(monthKey) {
  const [year, month] = monthKey.split("-").map(Number);
  const monthDate = new Date(year, month - 1, 1);
  monthLabel.textContent = monthDate.toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}

function renderTotals(payload) {
  totalsGrid.innerHTML = "";
  state.participants.forEach((participant) => {
    const total = payload.totals[participant.id] || 0;
    const card = document.createElement("article");
    card.className = "total-card";
    card.style.background = `linear-gradient(160deg, ${participant.color} 0%, ${participant.accent} 100%)`;
    card.innerHTML = `
      <div>
        <p>${participant.display_name}</p>
        <strong>${total}</strong>
      </div>
      <span>Total dog walks logged</span>
    `;
    totalsGrid.appendChild(card);
  });

  if (!payload.leader_id || payload.lead_delta === 0) {
    leadCopy.textContent = "You are currently tied. The spreadsheet can rest.";
    return;
  }

  const leader = participantById(payload.leader_id);
  leadCopy.textContent = `${leader.display_name} is ahead by ${payload.lead_delta} walk${payload.lead_delta === 1 ? "" : "s"}.`;
}

function renderBulkParticipantOptions() {
  if (bulkParticipant.options.length) {
    return;
  }
  state.participants.forEach((participant) => {
    const option = document.createElement("option");
    option.value = participant.id;
    option.textContent = participant.display_name;
    bulkParticipant.appendChild(option);
  });
}

function renderParticipantDialogButtons() {
  participantButtons.innerHTML = "";
  state.participants.forEach((participant) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "participant-button";
    button.style.background = `linear-gradient(135deg, ${participant.color} 0%, ${participant.accent} 100%)`;
    button.innerHTML = `<span>${participant.display_name}</span><span>${participant.short_name}</span>`;
    button.addEventListener("click", () => saveDayAssignment(participant.id));
    participantButtons.appendChild(button);
  });
}

function renderCalendarEvents(entries) {
  const events = entries.map((entry) => {
    const participant = participantById(entry.participant_id);
    return {
      id: entry.walk_date,
      title: participant.display_name,
      start: entry.walk_date,
      allDay: true,
      backgroundColor: participant.color,
      borderColor: participant.color,
      textColor: "#ffffff",
      sourceLabel: entry.source === "planned" ? "planned" : entry.source,
    };
  });

  state.calendar.removeAllEvents();
  events.forEach((event) => state.calendar.addEvent(event));
}

function openDayDialog(isoDate) {
  state.activeDate = isoDate;
  dialogDateLabel.textContent = new Date(`${isoDate}T12:00:00`).toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
  dialogStatus.textContent = "";
  dayDialog.showModal();
}

async function saveDayAssignment(participantId) {
  dialogStatus.textContent = "Saving...";
  const response = await fetch("/api/entries", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      walk_date: state.activeDate,
      participant_id: participantId,
      source: state.activeDate > state.today ? "planned" : "manual",
    }),
  });
  const payload = await response.json();
  if (!payload.ok) {
    dialogStatus.textContent = payload.error || "Could not save this day.";
    return;
  }
  dayDialog.close();
  await loadMonth(state.currentMonth);
}

async function clearSelectedDay() {
  if (!state.activeDate) {
    return;
  }
  dialogStatus.textContent = "Clearing...";
  const response = await fetch(`/api/entries/${state.activeDate}`, { method: "DELETE" });
  const payload = await response.json();
  if (!payload.ok) {
    dialogStatus.textContent = payload.error || "Could not clear this day.";
    return;
  }
  dayDialog.close();
  await loadMonth(state.currentMonth);
}

async function submitBulkPlan(event) {
  event.preventDefault();
  bulkPlanStatus.textContent = "Saving range...";
  const formData = new FormData(event.currentTarget);
  const payload = Object.fromEntries(formData.entries());
  const response = await fetch("/api/entries/bulk-plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  bulkPlanStatus.textContent = result.ok
    ? `Planned ${result.planned_days} day${result.planned_days === 1 ? "" : "s"}.`
    : result.error || "Could not plan this range.";
  if (result.ok) {
    event.currentTarget.reset();
    await loadMonth(state.currentMonth);
  }
}

async function submitImport(event) {
  event.preventDefault();
  importResult.textContent = "Importing...";
  const formData = new FormData(event.currentTarget);
  const csvText = formData.get("csv_text");
  const response = await fetch("/api/import/csv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csv_text: csvText }),
  });
  const result = await response.json();
  importResult.textContent = JSON.stringify(result, null, 2);
  if (result.ok) {
    await loadMonth(state.currentMonth);
  }
}

async function submitSheetImport() {
  importResult.textContent = "Importing from Google Sheets...";
  const form = document.getElementById("importForm");
  const formData = new FormData(form);
  const sheetUrl = formData.get("sheet_url");
  const response = await fetch("/api/import/google-sheet", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sheet_url: sheetUrl }),
  });
  const result = await response.json();
  importResult.textContent = JSON.stringify(result, null, 2);
  if (result.ok) {
    await loadMonth(state.currentMonth);
  }
}

function participantById(participantId) {
  return state.participants.find((participant) => participant.id === participantId);
}

function todayMonthKey() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}
