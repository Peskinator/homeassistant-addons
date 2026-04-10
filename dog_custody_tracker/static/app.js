const state = {
  currentMonth: todayMonthKey(),
  today: null,
  participants: [],
  entries: [],
  entriesByDate: new Map(),
  totals: {},
  calendar: null,
  suppressCalendarFetch: false,
  selectedDates: [],
  activeTab: "calendar",
};

const participantButtons = document.getElementById("participantButtons");
const dayDialog = document.getElementById("dayDialog");
const dialogDateLabel = document.getElementById("dialogDateLabel");
const dialogModeLabel = document.getElementById("dialogModeLabel");
const dialogStatus = document.getElementById("dialogStatus");
const selectionSummary = document.getElementById("selectionSummary");
const clearSelectionButton = document.getElementById("clearSelectionButton");
const clearEntryButton = document.getElementById("clearEntryButton");
const menuButton = document.getElementById("menuButton");
const appDrawer = document.getElementById("appDrawer");
const balanceHero = document.getElementById("balanceHero");
const balanceDelta = document.getElementById("balanceDelta");
const balanceCopy = document.getElementById("balanceCopy");
const leftParticipant = document.getElementById("leftParticipant");
const rightParticipant = document.getElementById("rightParticipant");

menuButton.addEventListener("click", toggleDrawer);
document.querySelectorAll(".drawer-link").forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.tab));
});
clearEntryButton.addEventListener("click", clearSelectedDay);
clearSelectionButton.addEventListener("click", clearCalendarSelection);

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
}

initializeCalendar();

function initializeCalendar() {
  const calendarEl = document.getElementById("calendar");
  state.calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: "dayGridMonth",
    initialDate: `${state.currentMonth}-01`,
    firstDay: 1,
    height: "auto",
    fixedWeekCount: false,
    selectable: true,
    selectMirror: true,
    unselectAuto: false,
    selectLongPressDelay: 180,
    longPressDelay: 180,
    headerToolbar: {
      left: "prev,next today",
      center: "title",
      right: "",
    },
    buttonText: {
      today: "Today",
    },
    dayCellClassNames: (arg) => dayCellClasses(arg.date),
    dateClick: (info) => {
      clearCalendarSelection();
      setSelectedDates([info.dateStr]);
      openDayDialog([info.dateStr]);
    },
    eventClick: (info) => {
      info.jsEvent.preventDefault();
      clearCalendarSelection();
      setSelectedDates([info.event.startStr]);
      openDayDialog([info.event.startStr]);
    },
    select: (info) => {
      const dates = datesFromExclusiveRange(info.startStr, info.endStr);
      setSelectedDates(dates);
      openDayDialog(dates);
    },
    unselect: () => {
      if (!state.selectedDates.length) {
        renderSelectionSummary();
      }
    },
    datesSet: (info) => {
      const marker = new Date(info.start);
      marker.setDate(marker.getDate() + 15);
      const monthKey = `${marker.getFullYear()}-${String(marker.getMonth() + 1).padStart(2, "0")}`;
      const rangeStart = toIsoDate(info.start);
      const rangeEnd = toIsoDate(info.end);
      if (
        state.suppressCalendarFetch &&
        monthKey === state.currentMonth
      ) {
        state.suppressCalendarFetch = false;
        return;
      }
      state.currentMonth = monthKey;
      loadMonth(monthKey, rangeStart, rangeEnd);
    },
    eventContent: (arg) => {
      const participant = participantById(arg.event.extendedProps.participantId);
      const wrapper = document.createElement("div");
      wrapper.className = "fc-event-card";
      wrapper.style.setProperty("--event-color", participant.color);

      const avatar = document.createElement("img");
      avatar.className = "event-avatar";
      avatar.src = participant.photo;
      avatar.alt = participant.display_name;

      wrapper.appendChild(avatar);

      if (arg.event.extendedProps.sourceLabel === "planned") {
        const meta = document.createElement("span");
        meta.className = "event-source";
        meta.textContent = "planned";
        wrapper.appendChild(meta);
      }

      return { domNodes: [wrapper] };
    },
  });
  state.calendar.render();
}

async function loadMonth(monthKey = state.currentMonth, rangeStart = null, rangeEnd = null) {
  const params = new URLSearchParams({ month: monthKey });
  if (rangeStart) {
    params.set("range_start", rangeStart);
  }
  if (rangeEnd) {
    params.set("range_end", rangeEnd);
  }
  const response = await fetch(`/api/bootstrap?${params.toString()}`);
  const payload = await response.json();
  state.currentMonth = payload.month;
  state.today = payload.today;
  state.participants = payload.participants;
  state.entries = payload.entries;
  state.entriesByDate = new Map(payload.entries.map((entry) => [entry.walk_date, entry]));
  state.totals = payload.totals;
  render(payload);
}

function render(payload) {
  renderBalance(payload);
  renderParticipantDialogButtons();
  renderCalendarEvents(payload.entries);
  renderSelectionSummary();
}

function renderBalance(payload) {
  const ordered = [...state.participants].sort((left, right) => {
    return (payload.totals[right.id] || 0) - (payload.totals[left.id] || 0);
  });
  const leader = ordered[0];
  const trailing = ordered[1];
  const leadDelta = payload.lead_delta || 0;

  leftParticipant.innerHTML = buildBalanceParticipantCard(leader, true);
  rightParticipant.innerHTML = buildBalanceParticipantCard(trailing, false);

  balanceHero.style.background = `linear-gradient(135deg, ${leader.color}22 0%, ${trailing.color}22 100%)`;

  if (!payload.leader_id || leadDelta === 0) {
    balanceDelta.textContent = "Tied";
    balanceCopy.textContent = "Both of you are perfectly even right now.";
    return;
  }

  balanceDelta.textContent = `${leadDelta}`;
  balanceCopy.textContent = `${leader.display_name} is ahead right now.`;
}

function buildBalanceParticipantCard(participant, isLeader) {
  return `
    <div class="balance-avatar-wrap ${isLeader ? "is-leading" : ""}" style="--participant-color:${participant.color}; --participant-accent:${participant.accent};">
      ${isLeader ? '<span class="leader-crown" aria-hidden="true">👑</span>' : ""}
      <img class="balance-avatar" src="${participant.photo}" alt="${participant.display_name}">
    </div>
    <span class="balance-name">${participant.display_name}</span>
  `;
}

function renderParticipantDialogButtons() {
  participantButtons.innerHTML = "";
  state.participants.forEach((participant) => {
    const button = buildParticipantButton(participant, async () => {
      await saveAssignment(participant.id);
    });
    participantButtons.appendChild(button);
  });
}

function buildParticipantButton(participant, onClick, avatarOnly = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "participant-button";
  button.style.background = `linear-gradient(135deg, ${participant.color} 0%, ${participant.accent} 100%)`;
  button.innerHTML = avatarOnly
    ? `<img class="participant-button-avatar" src="${participant.photo}" alt="${participant.display_name}"><span>${participant.display_name}</span>`
    : `<img class="participant-button-avatar" src="${participant.photo}" alt="${participant.display_name}"><span>${participant.display_name}</span><span>${participant.short_name}</span>`;
  button.addEventListener("click", onClick);
  return button;
}

function renderCalendarEvents(entries) {
  const events = entries
    .filter((entry) => shouldRenderStreakAvatar(entry))
    .map((entry) => {
      const participant = participantById(entry.participant_id);
      return {
        id: entry.walk_date,
        title: participant.display_name,
        start: entry.walk_date,
        allDay: true,
        backgroundColor: "transparent",
        borderColor: "transparent",
        textColor: "#ffffff",
        participantId: participant.id,
        sourceLabel: entry.source === "planned" ? "planned" : entry.source,
      };
    });

  state.calendar.removeAllEvents();
  events.forEach((event) => state.calendar.addEvent(event));
}

function shouldRenderStreakAvatar(entry) {
  const previousEntry = state.entriesByDate.get(shiftIsoDate(entry.walk_date, -1));
  const nextEntry = state.entriesByDate.get(shiftIsoDate(entry.walk_date, 1));
  const sameAsPrevious = previousEntry?.participant_id === entry.participant_id;
  const sameAsNext = nextEntry?.participant_id === entry.participant_id;
  return !sameAsPrevious || !sameAsNext;
}

function shiftIsoDate(isoDate, offsetDays) {
  const value = new Date(`${isoDate}T12:00:00`);
  value.setDate(value.getDate() + offsetDays);
  return value.toISOString().slice(0, 10);
}

function toIsoDate(value) {
  return new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function setSelectedDates(dates) {
  state.selectedDates = [...new Set(dates)].sort();
  clearSelectionButton.classList.toggle("is-hidden", state.selectedDates.length === 0);
  refreshSelectedCells();
  renderSelectionSummary();
}

function clearCalendarSelection() {
  state.selectedDates = [];
  clearSelectionButton.classList.add("is-hidden");
  state.calendar.unselect();
  refreshSelectedCells();
  renderSelectionSummary();
}

function renderSelectionSummary() {
  const count = state.selectedDates.length;

  if (count === 0) {
    selectionSummary.textContent = "Tap once for a single day or drag across days to bulk assign.";
    return;
  }

  if (count === 1) {
    selectionSummary.textContent = `1 date selected: ${formatLongDate(state.selectedDates[0])}`;
    return;
  }

  selectionSummary.textContent = `${count} dates selected from ${formatShortDate(state.selectedDates[0])} to ${formatShortDate(state.selectedDates[count - 1])}.`;
}

function openDayDialog(dates) {
  const uniqueDates = [...new Set(dates)].sort();
  dialogStatus.textContent = "";

  if (uniqueDates.length === 1) {
    dialogModeLabel.textContent = "Choose the walker";
    dialogDateLabel.textContent = formatLongDate(uniqueDates[0]);
    clearEntryButton.textContent = "Clear this day";
  } else {
    dialogModeLabel.textContent = "Assign selected days";
    dialogDateLabel.textContent = `${uniqueDates.length} dates selected`;
    clearEntryButton.textContent = `Clear ${uniqueDates.length} days`;
  }

  dayDialog.dataset.selectedDates = JSON.stringify(uniqueDates);
  dayDialog.showModal();
}

async function saveAssignment(participantId) {
  const selectedDates = JSON.parse(dayDialog.dataset.selectedDates || "[]");
  dialogStatus.textContent = "Saving...";

  let response;
  if (selectedDates.length > 1) {
    response = await fetch("/api/entries/assign-dates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dates: selectedDates,
        participant_id: participantId,
      }),
    });
  } else {
    response = await fetch("/api/entries", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        walk_date: selectedDates[0],
        participant_id: participantId,
        source: selectedDates[0] > state.today ? "planned" : "manual",
      }),
    });
  }

  const payload = await response.json();
  if (!payload.ok) {
    dialogStatus.textContent = payload.error || "Could not save this selection.";
    return;
  }

  dayDialog.close();
  await loadMonth(state.currentMonth);
}

async function clearSelectedDay() {
  const selectedDates = JSON.parse(dayDialog.dataset.selectedDates || "[]");
  if (!selectedDates.length) {
    dialogStatus.textContent = "No selected days to clear.";
    return;
  }

  dialogStatus.textContent = selectedDates.length === 1 ? "Clearing..." : `Clearing ${selectedDates.length} days...`;
  const results = await Promise.all(
    selectedDates.map(async (walkDate) => {
      const response = await fetch(`/api/entries/${walkDate}`, { method: "DELETE" });
      return response.json();
    }),
  );
  const failed = results.find((payload) => !payload.ok);
  if (failed) {
    dialogStatus.textContent = failed.error || "Could not clear the selected days.";
    return;
  }

  dayDialog.close();
  clearCalendarSelection();
  await loadMonth(state.currentMonth);
}

function toggleDrawer() {
  const nextState = appDrawer.classList.toggle("is-hidden");
  menuButton.setAttribute("aria-expanded", String(!nextState));
}

function activateTab(tabId) {
  state.activeTab = tabId;
  document.querySelectorAll(".drawer-link").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tab === tabId);
  });
  document.querySelectorAll("[data-tab-panel]").forEach((panel) => {
    panel.classList.toggle("is-hidden", panel.dataset.tabPanel !== tabId);
  });
  appDrawer.classList.add("is-hidden");
  menuButton.setAttribute("aria-expanded", "false");
  if (tabId === "calendar") {
    state.calendar.updateSize();
  }
}

function participantById(participantId) {
  return state.participants.find((participant) => participant.id === participantId);
}

function refreshSelectedCells() {
  document.querySelectorAll(".fc-daygrid-day").forEach((cell) => {
    const dateValue = cell.getAttribute("data-date");
    cell.classList.toggle("manual-selected", state.selectedDates.includes(dateValue));
  });
}

function dayCellClasses(dateValue) {
  const isoDate = toIsoDate(dateValue);
  const entry = state.entriesByDate.get(isoDate);
  if (!entry) {
    return [];
  }
  return ["has-assignment", `has-assignment-${entry.participant_id}`];
}

function datesFromExclusiveRange(startStr, endStr) {
  const dates = [];
  const cursor = new Date(`${startStr}T12:00:00`);
  const exclusiveEnd = new Date(`${endStr}T12:00:00`);
  while (cursor < exclusiveEnd) {
    dates.push(toIsoDate(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }
  return dates;
}

function formatLongDate(isoDate) {
  return new Date(`${isoDate}T12:00:00`).toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function formatShortDate(isoDate) {
  return new Date(`${isoDate}T12:00:00`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function todayMonthKey() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function toIsoDate(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
