const TOKEN_KEY = "onee_faceid_access_token";
const ACCOUNT_KEY = "onee_faceid_account";

const accessToken = localStorage.getItem(TOKEN_KEY);
if (!accessToken) {
  window.location.replace("/login");
}

const state = {
  loading: false,
};

const elements = {
  dayInput: document.querySelector("#dayInput"),
  refreshButton: document.querySelector("#refreshButton"),
  generatedAt: document.querySelector("#generatedAt"),
  timezoneBadge: document.querySelector("#timezoneBadge"),
  statsGrid: document.querySelector("#statsGrid"),
  insideCount: document.querySelector("#insideCount"),
  currentPresenceBody: document.querySelector("#currentPresenceBody"),
  recognitionBreakdown: document.querySelector("#recognitionBreakdown"),
  trendChart: document.querySelector("#trendChart"),
  visitsBody: document.querySelector("#visitsBody"),
  recentPresenceBody: document.querySelector("#recentPresenceBody"),
  errorBox: document.querySelector("#errorBox"),
  accountName: document.querySelector("#accountName"),
  accountRole: document.querySelector("#accountRole"),
  logoutButton: document.querySelector("#logoutButton"),
};

function localIsoDate() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDateTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("fr-MA", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("fr-MA", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function statusClass(value) {
  return `status-${String(value ?? "").toLowerCase()}`;
}

function setLoading(value) {
  state.loading = value;
  elements.refreshButton.disabled = value;
  elements.refreshButton.textContent = value ? "Chargement…" : "Actualiser";
}

function showError(message) {
  elements.errorBox.textContent = message;
  elements.errorBox.classList.remove("hidden");
}

function clearError() {
  elements.errorBox.textContent = "";
  elements.errorBox.classList.add("hidden");
}

function renderStats(counts) {
  const items = [
    ["Agents actifs", counts.active_employees, "Profils employés actifs"],
    ["Visiteurs actifs", counts.active_visitors, "Profils visiteurs actifs"],
    ["Personnes enrôlées", counts.enrolled_people, "Avec embedding actif"],
    ["Présents maintenant", counts.currently_inside, "Dernier pointage = ENTRY"],
    ["Entrées", counts.entries_today, "Pour la journée choisie"],
    ["Sorties", counts.exits_today, "Pour la journée choisie"],
    ["Visites prévues", counts.visits_today, "Pour la journée choisie"],
    ["Visites en cours", counts.visits_in_progress, "Statut IN_PROGRESS"],
    ["Reconnaissances", counts.recognitions_today, "Toutes les décisions"],
    ["MATCHED", counts.matched_today, "Personnes reconnues"],
    ["UNKNOWN", counts.unknown_today, "Visages non identifiés"],
    ["Taux de succès", `${counts.recognition_success_rate.toFixed(1)} %`, "MATCHED / tentatives"],
  ];

  elements.statsGrid.innerHTML = items.map(([label, value, note]) => `
    <article class="stat-card">
      <div class="stat-label">${escapeHtml(label)}</div>
      <div class="stat-value">${escapeHtml(value)}</div>
      <div class="stat-note">${escapeHtml(note)}</div>
    </article>
  `).join("");
}

function renderCurrentPresence(items) {
  elements.insideCount.textContent = `${items.length} personne(s)`;
  if (!items.length) {
    elements.currentPresenceBody.innerHTML = '<tr><td class="empty" colspan="4">Aucune personne actuellement présente.</td></tr>';
    return;
  }

  elements.currentPresenceBody.innerHTML = items.map((item) => {
    const destination = item.unit_name || item.organization_name || "—";
    return `
      <tr>
        <td><strong>${escapeHtml(item.first_name)} ${escapeHtml(item.last_name)}</strong></td>
        <td>${escapeHtml(item.person_type)}</td>
        <td>${escapeHtml(destination)}</td>
        <td>${escapeHtml(formatDateTime(item.event_time))}</td>
      </tr>
    `;
  }).join("");
}

function renderBreakdown(items) {
  if (!items.length) {
    elements.recognitionBreakdown.innerHTML = '<p class="empty">Aucune reconnaissance pour cette journée.</p>';
    return;
  }

  const max = Math.max(...items.map((item) => item.count), 1);
  elements.recognitionBreakdown.innerHTML = items.map((item) => {
    const width = Math.max((item.count / max) * 100, 3);
    return `
      <div class="breakdown-row">
        <span class="breakdown-label">${escapeHtml(item.decision)}</span>
        <div class="progress" aria-label="${escapeHtml(item.decision)} : ${item.count}">
          <span style="width:${width}%"></span>
        </div>
        <span class="breakdown-count">${item.count}</span>
      </div>
    `;
  }).join("");
}

function renderTrend(items) {
  if (!items.length) {
    elements.trendChart.innerHTML = '<p class="empty">Aucune donnée disponible.</p>';
    return;
  }

  const max = Math.max(
    ...items.flatMap((item) => [item.entries, item.exits, item.matched]),
    1,
  );

  elements.trendChart.style.gridTemplateColumns = `repeat(${items.length}, minmax(90px, 1fr))`;
  elements.trendChart.innerHTML = items.map((item) => {
    const entryHeight = Math.max((item.entries / max) * 155, item.entries ? 5 : 2);
    const exitHeight = Math.max((item.exits / max) * 155, item.exits ? 5 : 2);
    const matchedHeight = Math.max((item.matched / max) * 155, item.matched ? 5 : 2);
    const dayLabel = new Intl.DateTimeFormat("fr-MA", { weekday: "short", day: "2-digit" })
      .format(new Date(`${item.day}T12:00:00`));

    return `
      <div class="trend-day">
        <div class="bars">
          <span class="bar entries" style="height:${entryHeight}px" title="Entrées : ${item.entries}"></span>
          <span class="bar exits" style="height:${exitHeight}px" title="Sorties : ${item.exits}"></span>
          <span class="bar matched" style="height:${matchedHeight}px" title="MATCHED : ${item.matched}"></span>
        </div>
        <span class="trend-label">${escapeHtml(dayLabel)}</span>
        <span class="trend-values">E ${item.entries} · S ${item.exits} · M ${item.matched}</span>
      </div>
    `;
  }).join("");
}

function renderVisits(items) {
  if (!items.length) {
    elements.visitsBody.innerHTML = '<tr><td class="empty" colspan="4">Aucune visite planifiée pour cette journée.</td></tr>';
    return;
  }

  elements.visitsBody.innerHTML = items.map((item) => {
    const destination = item.host_employee_name || item.host_unit_name || "—";
    return `
      <tr>
        <td>${escapeHtml(formatTime(item.planned_start))}</td>
        <td><strong>${escapeHtml(item.visitor_name)}</strong><br><small>${escapeHtml(item.organization_name)}</small></td>
        <td>${escapeHtml(destination)}<br><small>${escapeHtml(item.purpose)}</small></td>
        <td><span class="status ${statusClass(item.status)}">${escapeHtml(item.status)}</span></td>
      </tr>
    `;
  }).join("");
}

function renderRecentPresence(items) {
  if (!items.length) {
    elements.recentPresenceBody.innerHTML = '<tr><td class="empty" colspan="4">Aucun pointage enregistré.</td></tr>';
    return;
  }

  elements.recentPresenceBody.innerHTML = items.map((item) => `
    <tr>
      <td>${escapeHtml(formatDateTime(item.event_time))}</td>
      <td><strong>${escapeHtml(item.first_name)} ${escapeHtml(item.last_name)}</strong><br><small>${escapeHtml(item.person_type)}</small></td>
      <td><span class="status ${statusClass(item.event_type)}">${escapeHtml(item.event_type)}</span></td>
      <td>${escapeHtml(item.source)}</td>
    </tr>
  `).join("");
}

function renderDashboard(data) {
  elements.generatedAt.textContent = `Dernière actualisation : ${formatDateTime(data.generated_at)}`;
  elements.timezoneBadge.textContent = data.timezone;
  renderStats(data.counts);
  renderCurrentPresence(data.current_presence);
  renderBreakdown(data.recognition_breakdown);
  renderTrend(data.trend);
  renderVisits(data.visits);
  renderRecentPresence(data.recent_presence_events);
}

async function loadDashboard() {
  if (state.loading) return;
  setLoading(true);
  clearError();

  try {
    const day = elements.dayInput.value;
    const response = await fetch(`/dashboard/overview?day=${encodeURIComponent(day)}`, {
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
    });

    if (response.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(ACCOUNT_KEY);
      window.location.replace("/login");
      return;
    }

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `Erreur HTTP ${response.status}`);
    }

    const data = await response.json();
    renderDashboard(data);
  } catch (error) {
    showError(`Impossible de charger le tableau de bord : ${error.message}`);
  } finally {
    setLoading(false);
  }
}

elements.dayInput.value = localIsoDate();
elements.refreshButton.addEventListener("click", loadDashboard);
elements.dayInput.addEventListener("change", loadDashboard);
loadDashboard();


function renderConnectedAccount() {
  const raw = localStorage.getItem(ACCOUNT_KEY);
  if (!raw) return;
  try {
    const account = JSON.parse(raw);
    const person = account.person;
    elements.accountName.textContent = person
      ? `${person.first_name} ${person.last_name}`
      : account.username;
    elements.accountRole.textContent = account.role;
  } catch {
    elements.accountName.textContent = "Compte connecté";
  }
}

elements.logoutButton.addEventListener("click", () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(ACCOUNT_KEY);
  window.location.replace("/login");
});

renderConnectedAccount();
