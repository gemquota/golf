const $ = (id) => document.getElementById(id);
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
let payload = null;

function weekdayOf(isoDate) {
  const [year, month, day] = String(isoDate || "").split("-").map(Number);
  return WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
}
function formatDate(value) {
  if (!value) return "—";
  const [year, month, day] = String(value).split("-");
  return day && month && year ? `${day}/${month}/${year}` : value;
}
function money(value) {
  const number = Number(value);
  return value === null || value === "" || !Number.isFinite(number)
    ? "—" : new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD", maximumFractionDigits: 2 }).format(number);
}
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}
function siteLink(url, merchant) {
  const link = element("a", "site-link", merchant || url);
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.title = url;
  return link;
}
function empty(container, message) {
  container.replaceChildren(element("p", "empty-state", message));
}
function renderStats() {
  const analytics = payload.analytics || {};
  $("trackedDays").textContent = String((payload.runs || []).length);
  $("releaseCount").textContent = String(analytics.release_count || 0);
  $("siteCount").textContent = String(Object.keys(payload.site_baseline || {}).length);
  $("lastUpdate").textContent = analytics.generated_at
    ? new Date(analytics.generated_at).toLocaleString("en-AU", { dateStyle: "medium", timeStyle: "short" })
    : "Awaiting first run";
}
function renderWeekdayChart() {
  const host = $("weekdayChart");
  host.replaceChildren();
  const rows = payload.analytics?.weekday_releases || [];
  const max = Math.max(1, ...rows.map(row => Number(row.count) || 0));
  for (const row of rows) {
    const item = element("button", "weekday-item");
    item.type = "button";
    item.setAttribute("aria-label", `${row.weekday}: ${row.count} observed new commissions`);
    const label = element("span", "weekday-label", row.weekday);
    const track = element("span", "weekday-track");
    const bar = element("span", "weekday-bar");
    bar.style.width = `${Math.max(0, Number(row.count) || 0) / max * 100}%`;
    track.append(bar);
    const count = element("strong", "weekday-count", row.count);
    const share = element("small", "weekday-share", `${Math.round((Number(row.share) || 0) * 100)}%`);
    item.append(label, track, count, share);
    item.addEventListener("click", () => {
      $("weekdayFilter").value = row.weekday;
      renderCommissions();
      $("commissionList").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    host.append(item);
  }
  if (!rows.length) empty(host, "No history data yet. The first successful daily scrape creates the baseline; observed release patterns appear after subsequent scrapes.");
}
function commissionEvents() {
  return (payload.events || []).filter(event => event.type === "new_commission");
}
function renderCommissions() {
  const host = $("commissionList");
  const filter = $("weekdayFilter").value;
  const exactDate = $("dateFilter").value;
  const events = commissionEvents()
    .filter(event => (!exactDate || event.date === exactDate) &&
      (filter === "all" || weekdayOf(event.date) === filter))
    .sort((a, b) => String(b.date).localeCompare(String(a.date)) || String(a.merchant).localeCompare(String(b.merchant)));
  host.replaceChildren();
  if (!events.length) {
    empty(host, exactDate ? `No recorded commission releases on ${formatDate(exactDate)}.` : filter === "all" ? "No newly observed commission releases yet." : `No recorded commission releases first observed on ${filter}s yet.`);
    return;
  }
  for (const event of events.slice(0, 250)) {
    const card = element("article", "release-card");
    const top = element("div", "release-card-top");
    const name = element("strong", "release-name", event.bonus?.name || "Unnamed commission");
    const amount = element("strong", "release-amount", money(event.bonus?.amount));
    top.append(name, amount);
    const meta = element("div", "release-meta");
    meta.append(element("span", "release-date", `${weekdayOf(event.date)}, ${formatDate(event.date)}`));
    meta.append(siteLink(event.url, event.merchant || event.url));
    card.append(top, meta);
    const details = element("div", "release-details");
    const values = [
      ["Min withdrawal", event.bonus?.minwithdraw],
      ["Rollover", event.bonus?.rollover],
      ["Reset", event.bonus?.reset],
      ["Claim condition", event.bonus?.claimcondition]
    ].filter(([, value]) => value !== null && value !== undefined && value !== "");
    for (const [label, value] of values) details.append(element("span", "", `${label}: ${value}`));
    if (values.length) card.append(details);
    host.append(card);
  }
  if (events.length > 250) host.append(element("p", "empty-state", `Showing the latest 250 of ${events.length} matching releases.`));
}
function renderSites() {
  const host = $("siteRows");
  const search = $("siteSearch").value.trim().toLowerCase();
  const rows = (payload.analytics?.sites || []).filter(row =>
    `${row.merchant} ${row.url}`.toLowerCase().includes(search));
  host.replaceChildren();
  if (!rows.length) {
    const tr = element("tr");
    const td = element("td", "empty-cell", "No matching sites yet.");
    td.colSpan = 6;
    tr.append(td); host.append(tr); return;
  }
  for (const row of rows) {
    const tr = element("tr");
    const site = element("td"); site.append(siteLink(row.url, row.merchant));
    tr.append(site);
    tr.append(element("td", "", row.likely_weekday || "Not established"));
    tr.append(element("td", "numeric-cell", row.commission_release_count));
    const pattern = element("td", "pattern-cell");
    const topDays = (row.weekday_counts || []).filter(day => day.count > 0).slice(0, 3);
    if (!topDays.length) pattern.textContent = "No new commissions observed yet";
    else pattern.textContent = topDays.map(day => `${day.weekday} ${day.count}`).join(" · ");
    tr.append(pattern);
    tr.append(element("td", "", formatDate(row.last_commission_release)));
    tr.append(element("td", `confidence confidence-${row.confidence || "low"}`, row.confidence || "low"));
    host.append(tr);
  }
}
function renderChangeLog() {
  const host = $("changeLog");
  const events = [...(payload.events || [])].sort((a, b) =>
    String(b.date).localeCompare(String(a.date)) || String(a.type).localeCompare(String(b.type)));
  host.replaceChildren();
  if (!events.length) {
    empty(host, "No changes recorded yet. The tracker needs at least two successful observations of a site to detect changes.");
    return;
  }
  for (const event of events.slice(0, 150)) {
    const card = element("article", "change-card");
    const kind = {
      new_commission: ["NEW COMMISSION", "change-new"],
      new_bonus: ["NEW BONUS", "change-new"],
      changed_bonus: ["CHANGED", "change-updated"],
      disappeared_bonus: ["NO LONGER SEEN", "change-gone"]
    }[event.type] || [event.type, ""];
    const badge = element("span", `change-kind ${kind[1]}`, kind[0]);
    const description = element("strong", "change-description", event.bonus?.name || "Unnamed bonus");
    const meta = element("div", "change-meta");
    meta.append(element("span", "", `${formatDate(event.date)} · ${weekdayOf(event.date)}`));
    meta.append(siteLink(event.url, event.merchant || event.url));
    card.append(badge, description, meta);
    if (event.type === "changed_bonus" && event.previous) {
      card.append(element("p", "change-note",
        `Previous amount: ${money(event.previous.amount)} · Current amount: ${money(event.bonus?.amount)}`));
    }
    host.append(card);
  }
  if (events.length > 150) host.append(element("p", "empty-state", `Showing the latest 150 of ${events.length} changes.`));
}
async function init() {
  $("weekdayFilter").addEventListener("change", renderCommissions);
  $("dateFilter").addEventListener("change", renderCommissions);
  $("siteSearch").addEventListener("input", renderSites);
  try {
    const response = await fetch("./bonus-history.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`History data unavailable (HTTP ${response.status})`);
    payload = await response.json();
    renderStats(); renderWeekdayChart(); renderCommissions(); renderSites(); renderChangeLog();
    $("methodology").textContent = payload.analytics?.methodology?.caveat || "Release weekdays are estimates based on daily observations.";
  } catch (error) {
    payload = { runs: [], events: [], site_baseline: {}, analytics: { sites: [], weekday_releases: [], release_count: 0 } };
    renderStats(); renderWeekdayChart(); renderCommissions(); renderSites(); renderChangeLog();
    $("methodology").textContent = `${error.message}. The scheduled workflow also requires the GOLF_CONFIG_INI repository secret to be configured.`;
  }
}
init();
