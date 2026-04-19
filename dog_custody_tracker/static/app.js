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
  app: null,
  actor: null,
  browserActor: null,
  activityLoaded: false,
  statsRange: "90",
  statsLoaded: false,
  charts: {},
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
const buildTag = document.getElementById("buildTag");
const activityList = document.getElementById("activityList");
const activityActorLabel = document.getElementById("activityActorLabel");
const statsRangeSelect = document.getElementById("statsRangeSelect");
const balanceChartCanvas = document.getElementById("balanceChart");
const cumulativeChartCanvas = document.getElementById("cumulativeChart");
const monthlyChartCanvas = document.getElementById("monthlyChart");

menuButton.addEventListener("click", toggleDrawer);
document.querySelectorAll(".drawer-link").forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.tab));
});
clearEntryButton.addEventListener("click", clearSelectedDay);
clearSelectionButton.addEventListener("click", clearCalendarSelection);
dayDialog.addEventListener("close", () => clearCalendarSelection());
statsRangeSelect.addEventListener("change", async () => {
  state.statsRange = statsRangeSelect.value;
  state.statsLoaded = false;
  if (state.activeTab === "stats") {
    await loadStats(true);
  }
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register(`/sw.js?v=${window.__ASSET_VERSION__ || "dev"}`));
}

initializeCalendar();
const initialRange = currentCalendarRange();
loadMonth(state.currentMonth, initialRange?.start ?? null, initialRange?.end ?? null).catch((error) => {
  console.error("Initial month load failed", error);
  balanceCopy.textContent = "Could not load data.";
});

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
  state.app = payload.app;
  state.actor = payload.actor;
  await hydrateBrowserActor();
  render(payload);
}

async function hydrateBrowserActor(force = false) {
  if (state.browserActor && !force) {
    return state.browserActor;
  }

  try {
    const response = await fetch("/cdn-cgi/access/get-identity", {
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return state.browserActor;
    }
    const payload = await response.json();
    const email = canonicalEmail(payload?.email);
    const actor = actorFromEmail(email);
    if (actor) {
      state.browserActor = actor;
      state.actor = actor;
    }
  } catch (_error) {
    return state.browserActor;
  }

  return state.browserActor;
}

function actorFromEmail(email) {
  if (canonicalEmail(email) === canonicalEmail("francois.pesqui@gmail.com")) {
    return { id: "frank", name: "Frank", email, source: "cloudflare_identity_endpoint" };
  }
  if (canonicalEmail(email) === canonicalEmail("kurt.zuo@gmail.com")) {
    return { id: "kurt", name: "Kurt", email, source: "cloudflare_identity_endpoint" };
  }
  return null;
}

function canonicalEmail(value) {
  const email = String(value || "").trim().toLowerCase();
  const atIndex = email.indexOf("@");
  if (atIndex === -1) {
    return email;
  }
  let local = email.slice(0, atIndex);
  let domain = email.slice(atIndex + 1);
  if (domain === "gmail.com" || domain === "googlemail.com") {
    local = local.split("+", 1)[0].replaceAll(".", "");
    domain = "gmail.com";
  }
  return `${local}@${domain}`;
}

function appProbe() {
  const standalone = window.matchMedia?.("(display-mode: standalone)")?.matches || false;
  return {
    app_version: state.app?.version || null,
    app_mode: state.app?.mode || null,
    asset_version: window.__ASSET_VERSION__ || null,
    browser_actor: state.browserActor
      ? {
          id: state.browserActor.id,
          name: state.browserActor.name,
          email: state.browserActor.email,
          source: state.browserActor.source,
        }
      : null,
    display_mode: standalone ? "standalone" : "browser",
    source_param: new URLSearchParams(window.location.search).get("source"),
    href: window.location.href,
    referrer: document.referrer || null,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
    language: navigator.language || null,
    user_agent: navigator.userAgent || null,
  };
}

function currentCalendarRange() {
  if (!state.calendar?.view?.activeStart || !state.calendar?.view?.activeEnd) {
    return null;
  }
  return {
    start: toIsoDate(state.calendar.view.activeStart),
    end: toIsoDate(state.calendar.view.activeEnd),
  };
}

function render(payload) {
  renderBuildTag(payload.app);
  renderBalance(payload);
  renderParticipantDialogButtons();
  renderCalendarEvents(payload.entries);
  renderSelectionSummary();
}

function renderBuildTag(appMeta) {
  if (!appMeta) {
    return;
  }
  buildTag.textContent = `${appMeta.mode} v${appMeta.version}`;
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
  button.innerHTML = `<img class="participant-button-avatar" src="${participant.photo}" alt="${participant.display_name}"><span>${participant.display_name}</span>`;
  button.addEventListener("click", onClick);
  return button;
}

async function loadActivity(force = false) {
  if (state.activityLoaded && !force) {
    return;
  }
  const response = await fetch("/api/activity?limit=80");
  const payload = await response.json();
  if (!payload.ok) {
    throw new Error(payload.error || "Could not load activity.");
  }
  renderActivity(payload.items || []);
  state.activityLoaded = true;
}

async function loadStats(force = false) {
  if (state.statsLoaded && !force) {
    return;
  }
  const response = await fetch(`/api/stats?range=${encodeURIComponent(state.statsRange)}`);
  const payload = await response.json();
  if (!payload.ok) {
    throw new Error(payload.error || "Could not load stats.");
  }
  renderStats(payload);
  state.statsLoaded = true;
}

function renderActivity(items) {
  if (state.actor) {
    activityActorLabel.textContent = state.actor.email
      ? `Logged in as ${state.actor.name} (${state.actor.email})`
      : `Logged in as ${state.actor.name}`;
  } else {
    activityActorLabel.textContent = "";
  }

  if (!items.length) {
    activityList.innerHTML = '<p class="empty-state">No activity yet.</p>';
    return;
  }

  activityList.innerHTML = items.map((item) => activityItemMarkup(item)).join("");
}

function activityItemMarkup(item) {
  const actor = participantById(item.actor_id) || {
    display_name: item.actor_name || "Unknown",
    photo: "/icon-192.png",
  };
  const before = participantById(item.before_participant_id);
  const after = participantById(item.after_participant_id);
  const line = activityDescription(item, before, after);

  return `
    <article class="activity-item">
      <img class="activity-avatar" src="${actor.photo}" alt="${actor.display_name}">
      <div class="activity-body">
        <div class="activity-topline">
          <strong>${actor.display_name}</strong>
          <span class="activity-time">${formatActivityTime(item.timestamp)}</span>
        </div>
        <p class="activity-copy">${line}</p>
      </div>
    </article>
  `;
}

function activityDescription(item, before, after) {
  const dayLabel = formatShortDate(item.walk_date);

  if (!before && after) {
    return `➕ Added ${after.display_name} on ${dayLabel}`;
  }

  if (before && !after) {
    return `➖ Removed ${before.display_name} from ${dayLabel}`;
  }

  if (before && after && before.id !== after.id) {
    return `🔄 Swapped ${dayLabel}: ${before.display_name} → ${after.display_name}`;
  }

  if (after) {
    return `✏️ Updated ${dayLabel} for ${after.display_name}`;
  }

  return `✏️ Updated ${dayLabel}`;
}

function renderStats(payload) {
  renderBalanceChart(payload);
  renderCumulativeChart(payload);
  renderMonthlyChart(payload);
}

function renderBalanceChart(payload) {
  replaceChart("balance", balanceChartCanvas, {
    type: "line",
    data: {
      labels: payload.labels.map(formatChartDate),
      datasets: [{
        label: "Balance",
        data: payload.balance_series,
        borderColor: "#1d201b",
        backgroundColor: "rgba(29, 32, 27, 0.12)",
        fill: true,
        pointRadius: 0,
        tension: 0.28,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      scales: {
        y: {
          ticks: { color: "#6b665c" },
          grid: { color: "rgba(29, 32, 27, 0.08)" },
        },
        x: {
          ticks: { color: "#6b665c", maxTicksLimit: 8 },
          grid: { display: false },
        },
      },
    },
  });
}

function renderCumulativeChart(payload) {
  const frank = participantById("frank");
  const kurt = participantById("kurt");
  replaceChart("cumulative", cumulativeChartCanvas, {
    type: "line",
    data: {
      labels: payload.labels.map(formatChartDate),
      datasets: [
        {
          label: frank.display_name,
          data: payload.cumulative_series.frank,
          borderColor: frank.color,
          backgroundColor: frank.accent,
          pointRadius: 0,
          tension: 0.24,
        },
        {
          label: kurt.display_name,
          data: payload.cumulative_series.kurt,
          borderColor: kurt.color,
          backgroundColor: kurt.accent,
          pointRadius: 0,
          tension: 0.24,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" },
      },
      scales: {
        y: {
          ticks: { color: "#6b665c" },
          grid: { color: "rgba(29, 32, 27, 0.08)" },
        },
        x: {
          ticks: { color: "#6b665c", maxTicksLimit: 8 },
          grid: { display: false },
        },
      },
    },
  });
}

function renderMonthlyChart(payload) {
  const frank = participantById("frank");
  const kurt = participantById("kurt");
  replaceChart("monthly", monthlyChartCanvas, {
    type: "bar",
    data: {
      labels: payload.monthly_labels.map(formatMonthLabel),
      datasets: [
        {
          label: frank.display_name,
          data: payload.monthly_labels.map((month) => payload.monthly_totals.frank?.[month] || 0),
          backgroundColor: frank.accent,
          borderColor: frank.color,
          borderWidth: 1,
          borderRadius: 8,
        },
        {
          label: kurt.display_name,
          data: payload.monthly_labels.map((month) => payload.monthly_totals.kurt?.[month] || 0),
          backgroundColor: kurt.accent,
          borderColor: kurt.color,
          borderWidth: 1,
          borderRadius: 8,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { color: "#6b665c" },
          grid: { color: "rgba(29, 32, 27, 0.08)" },
        },
        x: {
          ticks: { color: "#6b665c" },
          grid: { display: false },
        },
      },
    },
  });
}

function replaceChart(key, canvas, config) {
  if (state.charts[key]) {
    state.charts[key].destroy();
  }
  state.charts[key] = new Chart(canvas, config);
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
    selectionSummary.textContent = "Tap for one day or drag across days to assign.";
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
  await hydrateBrowserActor(true);
  const actorEmail = state.browserActor?.email || null;

  let response;
  if (selectedDates.length > 1) {
    response = await fetch("/api/entries/assign-dates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dates: selectedDates,
        participant_id: participantId,
        actor_email: actorEmail,
        actor_probe: {
          email: actorEmail,
          source: state.browserActor?.source || null,
          resolved: Boolean(state.browserActor),
        },
        app_probe: appProbe(),
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
        actor_email: actorEmail,
        actor_probe: {
          email: actorEmail,
          source: state.browserActor?.source || null,
          resolved: Boolean(state.browserActor),
        },
        app_probe: appProbe(),
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
  state.activityLoaded = false;
  state.statsLoaded = false;
  if (state.activeTab === "activity") {
    await loadActivity(true);
  }
  if (state.activeTab === "stats") {
    await loadStats(true);
  }
}

async function clearSelectedDay() {
  const selectedDates = JSON.parse(dayDialog.dataset.selectedDates || "[]");
  if (!selectedDates.length) {
    dialogStatus.textContent = "No selected days to clear.";
    return;
  }

  await hydrateBrowserActor(true);
  const actorEmail = state.browserActor?.email || null;
  dialogStatus.textContent = selectedDates.length === 1 ? "Clearing..." : `Clearing ${selectedDates.length} days...`;
  const results = await Promise.all(
    selectedDates.map(async (walkDate) => {
      const response = await fetch(`/api/entries/${walkDate}`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          actor_email: actorEmail,
          actor_probe: {
            email: actorEmail,
            source: state.browserActor?.source || null,
            resolved: Boolean(state.browserActor),
          },
          app_probe: appProbe(),
        }),
      });
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
  state.activityLoaded = false;
  state.statsLoaded = false;
  if (state.activeTab === "activity") {
    await loadActivity(true);
  }
  if (state.activeTab === "stats") {
    await loadStats(true);
  }
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
  if (tabId === "activity") {
    loadActivity().catch((error) => {
      console.error("Could not load activity", error);
      activityList.innerHTML = '<p class="empty-state">Could not load activity.</p>';
    });
  }
  if (tabId === "stats") {
    loadStats().catch((error) => {
      console.error("Could not load stats", error);
      balanceChartCanvas.closest(".stats-chart-grid").innerHTML = '<p class="empty-state">Could not load stats.</p>';
    });
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
  const classes = ["has-assignment", `has-assignment-${entry.participant_id}`];
  if (entry.source === "planned") {
    classes.push("is-planned");
  }
  return classes;
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

function formatActivityTime(isoTimestamp) {
  return new Date(isoTimestamp).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatChartDate(isoDate) {
  return new Date(`${isoDate}T12:00:00`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function formatMonthLabel(monthKey) {
  const [year, month] = monthKey.split("-");
  return new Date(Number(year), Number(month) - 1, 1).toLocaleDateString(undefined, {
    month: "short",
    year: "numeric",
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
