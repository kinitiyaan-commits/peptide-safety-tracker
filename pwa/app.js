/* app.js — static PWA for the Peptide Safety Tracker.
 *
 * Fully client-side: all records live in IndexedDB (store.js) on this
 * device; nothing is transmitted to any server. The only outbound links
 * are official FDA / DailyMed pages the user opens by choice, and no
 * personal data is included in those links.
 *
 * Not medical advice. No dose recommendations. No brand ratings.
 * Explicit units only: mcg / mg / IU / units / mL.
 */

/* eslint-disable no-use-before-define */

const UNITS = STATIC_DATA.UNITS;              // ["mcg","mg","IU","units","mL"]
const CATALOG = STATIC_DATA.CATALOG;
const ALIASES = STATIC_DATA.ALIASES;
const GOALS = STATIC_DATA.GOALS;
const GOAL_ORDER = ["sleep","recovery","energy","mood","appetite","digestion",
  "joints","skin","libido","bodyweight","height","treatment","symptoms",
  "appearance","growth_clinician","visit_prep","recordkeeping","custom"];
const COMMON_GOALS = ["sleep","bodyweight","energy","recovery","symptoms","appearance"];
const STATUS_LABEL = {
  "fda-approved": "Approved products exist (ingredient-level — verify exact product)",
  "not-fda-approved": "No FDA-approved product",
  "compounding-flagged": "FDA compounding context",
  "unknown": "Status not established here",
};
const DISCLAIMER =
  "This app records what you enter, never recommends doses, and never rates " +
  "brands as safe or unsafe. Many research peptides are not FDA-approved, and " +
  "compounded copies carry FDA-documented risks. Not medical advice — verify " +
  "anything important with official sources and a licensed clinician.";

// ---------------- tiny helpers ----------------
const $ = (sel) => document.querySelector(sel);
const esc = (s) => { const d = document.createElement("div"); d.textContent = s ?? ""; return d.innerHTML; };
const uid = () => "e_" + crypto.randomUUID();
const nowISO = () => new Date().toISOString();
const localDT = () => {
  const d = new Date(), off = d.getTimezoneOffset();
  return new Date(d - off * 60000).toISOString().slice(0, 16);
};
const toLocalInput = (iso) => {
  const d = new Date(iso); if (isNaN(d)) return localDT();
  const off = d.getTimezoneOffset();
  return new Date(d - off * 60000).toISOString().slice(0, 16);
};
const fmtWhen = (iso) => isNaN(new Date(iso)) ? esc(iso) :
  new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

let profile = null;         // active profile row
let goalsKeys = [];         // active profile's selected goal keys
let moreGoalsOpen = false;
let editingUsageId = null, editingObservationId = null;
let lastUsage = [], lastSymptoms = [], lastObservations = [], lastReminders = [];
let catalogIndex = null;    // lowercase name -> entry

function toast(msg, isWarn = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "fixed left-1/2 -translate-x-1/2 bottom-24 z-[80] px-4 py-2.5 rounded-xl text-sm shadow-xl max-w-[92vw] text-center " +
    (isWarn ? "bg-amber-600 text-white" : "bg-emerald-600 text-white");
  t.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), 4000);
}

// ---------------- boot ----------------
async function init() {
  catalogIndex = {};
  for (const c of CATALOG) {
    catalogIndex[c.name.toLowerCase()] = c;
    for (const a of (ALIASES[c.name] || [])) catalogIndex[String(a).toLowerCase()] = c;
  }
  $("#disclaimer-line").textContent =
    "This app is not medical advice; many research peptides are not FDA-approved.";
  $("#disclaimer-more").textContent = DISCLAIMER;

  const activeId = await Store.getMeta("activeProfileId");
  const profiles = await Store.profiles();
  profile = profiles.find(p => p.id === activeId) || profiles[0] || null;
  if (!profile) {
    $("#first-run").classList.remove("hidden");
  }
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
  }
  await loadAll();
  window.addEventListener("online", () => $("#offline-badge").classList.add("hidden"));
  window.addEventListener("offline", () => $("#offline-badge").classList.remove("hidden"));
  if (!navigator.onLine) $("#offline-badge").classList.remove("hidden");
}

async function loadAll() {
  if (!profile) return;
  goalsKeys = (await Store.goalsFor(profile.id)).goalKeys || [];
  lastUsage = await Store.byProfile("usage", profile.id);
  lastSymptoms = await Store.byProfile("symptoms", profile.id);
  lastObservations = await Store.byProfile("observations", profile.id);
  lastReminders = await Store.byProfile("reminders", profile.id);
  renderToday(); renderHistory(); renderCatalog(); renderSettings();
  renderGoalChips(); renderProfileBadge();
}

async function switchProfile(id) {
  profile = (await Store.profiles()).find(p => p.id === id) || null;
  await Store.setMeta("activeProfileId", profile ? profile.id : null);
  await loadAll();
}

function renderProfileBadge() {
  $("#profile-badge").textContent = profile ? profile.name : "No profile";
}

// ---------------- TODAY ----------------
function renderToday() {
  if (!profile) return;
  $("#today-date").textContent = new Date().toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
  const due = dueReminders();
  $("#dash-sub").textContent =
    `${lastUsage.length} dose${lastUsage.length === 1 ? "" : "s"} · ` +
    `${lastSymptoms.length} symptom${lastSymptoms.length === 1 ? "" : "s"} · ` +
    `${lastObservations.length} observation${lastObservations.length === 1 ? "" : "s"} logged for ${profile.name}`;
  const recent = lastUsage.slice(0, 3);
  $("#today-recent").innerHTML = recent.length
    ? recent.map(u => `
      <div class="flex justify-between items-center bg-slate-950 border border-slate-800 rounded-xl px-4 py-3">
        <div><span class="font-semibold text-sm">${esc(u.peptideName)}</span>
          <span class="text-xs text-slate-400 ml-1">${esc(u.amount)} ${esc(u.unit)}</span>
          ${u.notes ? `<div class="text-xs text-slate-500">${esc(u.notes)}</div>` : ""}
        </div>
        <span class="text-xs text-slate-500">${fmtWhen(u.takenAt)}</span>
      </div>`).join("")
    : `<p class="text-xs text-slate-500">Nothing logged yet today or earlier for this profile.</p>`;
  $("#today-reminders").innerHTML = due.length
    ? due.map(r => `
      <div class="bg-amber-950/30 border border-amber-900/60 rounded-xl px-4 py-3 flex items-center justify-between">
        <div><span class="text-sm font-semibold">${esc(r.peptideName)}</span>
          <span class="text-xs text-amber-300 ml-2">due ${esc(r.timeOfDay)}</span></div>
        <button onclick="openFabChooser()" class="text-xs text-amber-200 underline">Log</button>
      </div>`).join("")
    : "";
}

function dueReminders() {
  // In-app-only display: a reminder is "due" if its time has passed today
  // and it is enabled for today. Never delivered when the app is closed.
  const day = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][new Date().getDay()];
  const nowHHMM = localDT().slice(11, 16);
  return lastReminders.filter(r => r.enabled !== false)
    .filter(r => r.days.includes("Every day") || r.days.includes(day))
    .filter(r => r.timeOfDay <= nowHHMM);
}

// ---------------- FAB chooser + sheets ----------------
function openFabChooser() { $("#fab-chooser").classList.remove("hidden"); }
function closeFabChooser() { $("#fab-chooser").classList.add("hidden"); }
function closeLogSheet() { editingUsageId = null; $("#log-sheet").classList.add("hidden"); }
function closeSymptomSheet() { $("#symptom-sheet").classList.add("hidden"); }
function closeObservationSheet() { editingObservationId = null; $("#observation-sheet").classList.add("hidden"); }

function openLogSheet(entryId) {
  editingUsageId = entryId || null;
  const form = $("#log-sheet form");
  form.dataset.idem = crypto.randomUUID();
  delete form.dataset.override;
  $("#log-sheet-title").textContent = editingUsageId ? "Correct entry" : "Log a dose";
  $("#u-submit-label").textContent = editingUsageId ? "Save correction" : "Save entry";
  form.reset();                                   // A.1: always open blank
  if (editingUsageId) {
    const e = lastUsage.find(x => x.id === editingUsageId);
    if (e) {
      $("#u-name").value = e.peptideName;
      $("#u-amount").value = e.amount;
      $("#u-unit").value = e.unit;
      $("#u-when").value = toLocalInput(e.takenAt);
      $("#u-notes").value = e.notes || "";
    }
  } else {
    $("#u-when").value = localDT();
  }
  clearErrors(form);
  $("#log-sheet").classList.remove("hidden");
  setTimeout(() => $("#u-name").focus(), 60);
}

function openSymptomSheet() {
  const form = $("#symptom-sheet form");
  form.reset();                                   // A.1: always open blank
  $("#s-severity").value = "3";
  clearErrors(form);
  $("#symptom-sheet").classList.remove("hidden");
  setTimeout(() => $("#s-name").focus(), 60);
}

function openObservationSheet(entryId) {
  editingObservationId = entryId || null;
  const form = $("#observation-sheet form");
  form.dataset.idem = crypto.randomUUID();
  form.reset();                                   // A.1: always open blank
  const box = $("#observation-fields");
  box.innerHTML = goalsKeys.length
    ? goalsKeys.flatMap(k => GOALS[k] && GOALS[k].fields ? GOALS[k].fields : []).map(f =>
        `<div><label class="block text-xs text-slate-400 mb-1">${esc(f.label)}</label>${goalFieldInput(f)}</div>`).join("")
    : `<p class="text-sm text-amber-300">No tracking goals selected yet — pick some in Settings → Tracking goals to record observations.</p>`;
  if (editingObservationId) {
    const e = lastObservations.find(x => x.id === editingObservationId);
    if (e) {
      $("#o-when").value = toLocalInput(e.takenAt);
      $("#o-notes").value = e.notes || "";
      box.querySelectorAll(".gf").forEach(el => {
        const v = e.goalData && e.goalData[el.dataset.gkey];
        if (v !== undefined) el.value = v;
      });
    }
  } else {
    $("#o-when").value = localDT();
  }
  clearErrors(form);
  $("#observation-sheet").classList.remove("hidden");
}

function goalFieldInput(f) {
  if (f.type === "rating") {
    return `<select class="inp gf" data-gkey="${esc(f.key)}"><option value="">—</option>${[1,2,3,4,5].map(n => `<option value="${n}">${n}</option>`).join("")}</select>`;
  }
  if (f.type === "number") {
    return `<input type="number" step="any" class="inp gf" data-gkey="${esc(f.key)}" placeholder="optional">`;
  }
  return `<input type="text" maxlength="200" class="inp gf" data-gkey="${esc(f.key)}" placeholder="optional">`;
}

function collectGoalData() {
  const data = {};
  document.querySelectorAll("#observation-fields .gf").forEach(el => {
    if (el.value === "" || el.value == null) return;
    data[el.dataset.gkey] = el.value;
  });
  return Object.keys(data).length ? data : null;
}

function clearErrors(form) {
  const box = form.querySelector(".err");
  if (box) box.textContent = "";
  form.querySelectorAll(".invalid").forEach(el => el.classList.remove("invalid"));
}
function formError(sel, msg, input) {
  const box = $(sel);
  if (box) box.textContent = msg;
  if (input) input.classList.add("invalid");
}

// ---------------- submissions ----------------
async function logUsage(ev) {
  ev.preventDefault();
  const form = ev.target;
  clearErrors(form);
  const name = $("#u-name").value.trim();
  const amount = parseFloat($("#u-amount").value);
  const unit = $("#u-unit").value;
  if (!name) { formError("#u-error", "Enter a product or peptide name.", $("#u-name")); return; }
  if (!(amount > 0)) { formError("#u-error", "Amount must be a number greater than 0.", $("#u-amount")); return; }
  if (!UNITS.includes(unit)) { formError("#u-error", "Explicit unit required (mcg, mg, IU, units, mL)."); return; }
  const when = $("#u-when").value;
  const takenAt = when ? new Date(when).toISOString() : nowISO();
  const notes = $("#u-notes").value;

  if (editingUsageId) {
    const e = lastUsage.find(x => x.id === editingUsageId);
    if (e) {
      const changed = e.peptideName !== name || Number(e.amount) !== amount ||
        e.unit !== unit || e.takenAt !== takenAt || e.notes !== notes;
      if (changed) {
        e.corrections = e.corrections || [];
        e.corrections.push({ editedAt: nowISO(), previous: {
          peptideName: e.peptideName, amount: e.amount, unit: e.unit,
          takenAt: e.takenAt, notes: e.notes } });
        Object.assign(e, { peptideName: name, amount, unit, takenAt, notes });
        await Store.put("usage", e);
        toast("✓ Entry corrected — previous values kept in its correction history");
      } else toast("Nothing changed — no correction recorded");
    }
    closeLogSheet(); await loadAll(); return;
  }

  // duplicate guard (distinct from idempotency key): same product + amount +
  // unit within 30 minutes asks for a confirmation instead of silently
  // creating a second event. Saving again confirms the override.
  const isOverride = form.dataset.override === "1";
  if (!isOverride) {
    const dup = lastUsage.find(u => u.peptideName.toLowerCase() === name.toLowerCase() &&
      Number(u.amount) === amount && u.unit === unit &&
      Math.abs(new Date(u.takenAt) - new Date(takenAt)) < 30 * 60 * 1000);
    if (dup) {
      formError("#u-error", `Possible duplicate of the ${fmtWhen(dup.takenAt)} ${esc(name)} entry. Choose Save entry again to keep both.`);
      form.dataset.override = "1";
      return;
    }
  }

  const rec = { id: uid(), profileId: profile.id, peptideName: name, amount,
    unit, route: "unspecified", takenAt, notes, goalData: null, corrections: [] };
  await Store.put("usage", rec);
  delete form.dataset.override;
  form.reset();
  $("#u-when").value = localDT();
  closeLogSheet();
  toast(`✓ Saved ${name} (${amount} ${unit}) for ${fmtWhen(takenAt)}`);
  await loadAll();
}

async function logSymptom(ev) {
  ev.preventDefault();
  const form = ev.target;
  clearErrors(form);
  const name = $("#s-name").value.trim();
  const description = $("#s-desc").value.trim();
  const severity = parseInt($("#s-severity").value, 10);
  if (!name) { formError("#s-error", "Name the symptom (e.g., 'headache').", $("#s-name")); return; }
  if (!description) { formError("#s-error", "Describe what you felt.", $("#s-desc")); return; }
  if (!(severity >= 1 && severity <= 5)) { formError("#s-error", "Severity must be 1–5."); return; }
  await Store.put("symptoms", { id: uid(), profileId: profile.id, peptideName: name,
    severity, description, loggedAt: nowISO() });
  form.reset(); $("#s-severity").value = "3";
  closeSymptomSheet();
  toast(`✓ Symptom logged (${severity}/5)`);
  await loadAll();
}

async function logObservation(ev) {
  ev.preventDefault();
  const form = ev.target;
  clearErrors(form);
  const when = $("#o-when").value;
  const notes = $("#o-notes").value;
  const goalData = collectGoalData();
  if (!notes && !goalData) {
    formError("#o-error", "Add a note or at least one measurement."); return;
  }
  if (editingObservationId) {
    const e = lastObservations.find(x => x.id === editingObservationId);
    if (e) {
      const changed = e.takenAt !== (when ? new Date(when).toISOString() : nowISO()) ||
        e.notes !== notes || JSON.stringify(e.goalData) !== JSON.stringify(goalData);
      if (changed) {
        e.corrections = e.corrections || [];
        e.corrections.push({ editedAt: nowISO(), previous: {
          takenAt: e.takenAt, notes: e.notes, goalData: e.goalData } });
        Object.assign(e, { takenAt: when ? new Date(when).toISOString() : nowISO(),
          notes, goalData });
        await Store.put("observations", e);
        toast("✓ Observation corrected — previous values kept in its correction history");
      } else toast("Nothing changed — no correction recorded");
    }
    closeObservationSheet(); await loadAll(); return;
  }
  await Store.put("observations", { id: uid(), profileId: profile.id,
    takenAt: when ? new Date(when).toISOString() : nowISO(), notes, goalData, corrections: [] });
  closeObservationSheet();
  toast("✓ Observation saved");
  await loadAll();
}

function correctionHtml(corrections, labelOf) {
  return (corrections || []).length
    ? `<details class="mt-1"><summary class="text-xs text-slate-500 underline">Correction history (${corrections.length})</summary>
       <div class="text-xs text-slate-500 pt-1 space-y-1">${corrections.map(c =>
         `<div>${fmtWhen(c.editedAt)} — previously: ${labelOf(c.previous)}</div>`).join("")}</div></details>`
    : "";
}
const USAGE_PREV = p => `${esc(p.peptideName)} ${esc(p.amount)} ${esc(p.unit)} at ${fmtWhen(p.takenAt)}`;
const OBS_PREV = p => `${fmtWhen(p.takenAt)}${p.notes ? " — " + esc(p.notes) : ""}`;

// ---------------- HISTORY ----------------
function renderHistory() {
  if (!profile) return;
  const q = ($("#hist-q").value || "").toLowerCase();
  const type = $("#hist-type").value;
  const rows = [];
  if (type === "all" || type === "dose") lastUsage.forEach(u => rows.push({ kind: "dose", when: u.takenAt, u }));
  if (type === "all" || type === "symptom") lastSymptoms.forEach(s => rows.push({ kind: "symptom", when: s.loggedAt, s }));
  if (type === "all" || type === "observation") lastObservations.forEach(o => rows.push({ kind: "observation", when: o.takenAt, o }));
  const filtered = q
    ? rows.filter(r => JSON.stringify(r.u || r.s || r.o).toLowerCase().includes(q))
    : rows;
  filtered.sort((a, b) => String(b.when).localeCompare(String(a.when)));
  $("#history-list").innerHTML = filtered.length ? filtered.slice(0, 100).map(r => {
    if (r.kind === "dose") {
      const u = r.u;
      return `<div class="bg-slate-950 border border-slate-800 rounded-xl px-4 py-3">
        <div class="flex justify-between gap-3">
          <div><span class="text-xs font-bold text-emerald-400 uppercase">Dose</span>
            <p class="text-sm">${esc(u.peptideName)} — ${esc(u.amount)} ${esc(u.unit)}</p>
            ${u.notes ? `<p class="text-xs text-slate-400">${esc(u.notes)}</p>` : ""}
            ${u.goalData ? `<p class="text-xs text-slate-500">Measurements: ${esc(Object.entries(u.goalData).map(([k, v]) => k + " " + v).join(", "))}</p>` : ""}
            ${correctionHtml(u.corrections, USAGE_PREV)}
          </div>
          <div class="text-right shrink-0"><p class="text-xs text-slate-500">${fmtWhen(u.takenAt)}</p>
            <button onclick="openLogSheet('${u.id}')" class="text-xs text-emerald-400 underline">Correct</button></div>
        </div></div>`;
    }
    if (r.kind === "symptom") {
      const s = r.s;
      return `<div class="bg-slate-950 border border-slate-800 rounded-xl px-4 py-3">
        <div class="flex justify-between gap-3">
          <div><span class="text-xs font-bold text-amber-400 uppercase">Symptom</span>
            <p class="text-sm">${esc(s.peptideName)} <span class="text-xs text-amber-300">severity ${s.severity}/5</span></p>
            <p class="text-xs text-slate-400">${esc(s.description)}</p></div>
          <p class="text-xs text-slate-500 shrink-0">${fmtWhen(s.loggedAt)}</p>
        </div></div>`;
    }
    const o = r.o;
    return `<div class="bg-slate-950 border border-slate-800 rounded-xl px-4 py-3">
      <div class="flex justify-between gap-3">
        <div><span class="text-xs font-bold text-sky-400 uppercase">Observation</span>
          ${o.notes ? `<p class="text-sm">${esc(o.notes)}</p>` : ""}
          ${o.goalData ? `<p class="text-xs text-slate-300">${esc(Object.entries(o.goalData).map(([k, v]) => k + " " + v).join(", "))}</p>` : ""}
          ${correctionHtml(o.corrections, OBS_PREV)}
        </div>
        <div class="text-right shrink-0"><p class="text-xs text-slate-500">${fmtWhen(o.takenAt)}</p>
          <button onclick="openObservationSheet('${o.id}')" class="text-xs text-sky-400 underline">Correct</button></div>
      </div></div>`;
  }).join("")
    : `<p class="text-sm text-slate-500">No matching entries.</p>`;
}

// ---------------- CATALOG / LEARN ----------------
function renderCatalog() {
  const q = ($("#cat-q")?.value || "").toLowerCase();
  const list = CATALOG.filter(c => !q || c.name.toLowerCase().includes(q) ||
    (ALIASES[c.name] || []).some(a => a.toLowerCase().includes(q)));
  $("#catalog-list").innerHTML = list.map(c => {
    const awaiting = c.review_status === "awaiting-verification";
    return `<div class="bg-slate-950 border ${awaiting ? "border-dashed border-amber-700/60" : "border-slate-800"} rounded-xl px-4 py-3 space-y-1">
      <div class="flex justify-between items-start gap-2">
        <p class="font-semibold text-sm">${esc(c.name)}
          <span class="text-xs text-slate-500 font-normal">· ${esc(c.category)}</span></p>
        <span class="text-xs shrink-0 ${awaiting ? "text-amber-300" : "text-emerald-400"}">${esc(STATUS_LABEL[c.regulatory_status] || STATUS_LABEL.unknown)}${awaiting ? " · awaiting verification" : ""}</span>
      </div>
      <p class="text-xs text-slate-400 leading-relaxed">${esc(c.evidence_note)}</p>
      <p class="text-xs text-slate-500">Source: <a class="text-emerald-400 underline" href="${esc(c.source_url)}" target="_blank" rel="noopener">official page</a> · source verified by this app's developer, not clinically reviewed — this never implies safety or endorsement.</p>
      <button onclick="verifyLinks('${esc(c.name).replace(/'/g, "\\'")}')" class="text-xs text-emerald-400 underline">Verification links (DailyMed / FDA) →</button>
      ${awaiting ? `<p class="text-xs text-amber-300/90">Not yet verified against the cited source — treat as unconfirmed.</p>` : ""}
    </div>`;
  }).join("") || `<p class="text-sm text-slate-500">No matching catalog entry. An unlisted name can still be logged manually.</p>`;
}

function verifyLinks(name) {
  const q = encodeURIComponent(name);
  $("#verify-result").innerHTML = `
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-2">
      <p class="text-sm font-semibold">Verification links for "${esc(name)}"</p>
      <p class="text-xs text-slate-400">Links only — the app never interprets results and never rates a brand. Verify licensure, prescription status, and the exact product yourself.</p>
      <ul class="text-xs space-y-1 list-disc pl-4">
        <li><a class="text-emerald-400 underline" target="_blank" rel="noopener" href="https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=${q}">DailyMed label search</a></li>
        <li><a class="text-emerald-400 underline" target="_blank" rel="noopener" href="https://open.fda.gov/data/drug/">openFDA drug records</a></li>
        <li><a class="text-emerald-400 underline" target="_blank" rel="noopener" href="https://www.fda.gov/drugs/human-drug-compounding">FDA human drug compounding</a></li>
        <li><a class="text-emerald-400 underline" target="_blank" rel="noopener" href="https://www.fda.gov/consumers/buying-medicine-online">FDA: Buying Medicine Online</a></li>
      </ul>
    </div>`;
}

// ---------------- GOALS ----------------
function renderGoalChips() {
  const box = $("#goal-chips");
  const keys = GOAL_ORDER.filter(k => GOALS[k]);
  let shown = keys, hidden = 0;
  if (!moreGoalsOpen) {
    shown = keys.filter(k => COMMON_GOALS.includes(k));
    keys.forEach(k => { if (!COMMON_GOALS.includes(k) && goalsKeys.includes(k)) shown.push(k); });
    hidden = keys.length - shown.length;
  }
  box.innerHTML = shown.map(key => `
    <button type="button" class="chip ${goalsKeys.includes(key) ? "!border-emerald-500 !bg-emerald-950" : ""}"
      onclick="toggleGoal('${key}')">${goalsKeys.includes(key) ? "✓ " : ""}${esc(GOALS[key].label)}</button>`).join("")
    + (hidden ? `<button type="button" class="chip !border-slate-500" onclick="moreGoalsOpen=!moreGoalsOpen;renderGoalChips();">${moreGoalsOpen ? "− Fewer goals" : "+ More goals (" + hidden + ")"}</button>` : "")
    + (goalsKeys.length ? "" : `<span class="text-xs text-slate-500">No goals selected — observations show only notes.</span>`);
  const heightOn = goalsKeys.includes("height") || goalsKeys.includes("growth_clinician");
  $("#height-goal-note").classList.toggle("hidden", !heightOn);
}

async function toggleGoal(key) {
  goalsKeys = goalsKeys.includes(key) ? goalsKeys.filter(k => k !== key) : goalsKeys.concat([key]);
  await Store.setGoals(profile.id, goalsKeys);
  renderGoalChips();
}

// ---------------- REMINDERS (in-app only) ----------------
async function addReminder(ev) {
  ev.preventDefault();
  const name = $("#r-name").value.trim();
  const time = $("#r-time").value;
  if (!name) { toast("Reminder needs a product name", true); return; }
  if (!/^[0-2][0-9]:[0-5][0-9]$/.test(time)) { toast("Reminder needs a time", true); return; }
  const days = $("#r-days").value || "Every day";
  await Store.put("reminders", { id: uid(), profileId: profile.id, peptideName: name,
    timeOfDay: time, days, notes: $("#r-notes").value.trim(), enabled: true });
  $("#reminder-form").reset();
  toast("✓ Reminder saved — in-app only, shows while this app is open");
  await loadAll();
}
async function toggleReminder(id, enabled) {
  const r = lastReminders.find(x => x.id === id);
  if (r) { r.enabled = enabled; await Store.put("reminders", r); await loadAll(); }
}
async function deleteReminder(id) {
  await Store.delete("reminders", id);
  toast("Reminder deleted (nothing was delivered by it)");
  await loadAll();
}

// ---------------- SETTINGS ----------------
async function renderSettings() {
  const profiles = await Store.profiles();
  $("#profile-select").innerHTML = profiles.map(p =>
    `<option value="${esc(p.id)}" ${p.id === profile?.id ? "selected" : ""}>${esc(p.name)}</option>`).join("");
  $("#settings-goal-note").textContent = goalsKeys.length
    ? goalsKeys.map(k => GOALS[k] ? GOALS[k].label : k).join(", ")
    : "none selected";
  $("#reminders-list").innerHTML = lastReminders.length ? lastReminders.map(r => `
    <div class="flex items-center justify-between bg-slate-950 border border-slate-800 rounded-xl px-3 py-2.5">
      <div><span class="text-sm font-semibold">${esc(r.peptideName)}</span>
        <span class="text-xs text-slate-400 ml-2">${esc(r.timeOfDay)} · ${esc(r.days)}</span>
        ${r.enabled === false ? `<span class="text-xs text-slate-500 ml-2">paused</span>` : ""}</div>
      <div class="flex gap-2 shrink-0">
        <button onclick="toggleReminder('${r.id}', ${r.enabled === false})" class="text-xs text-emerald-400 underline">${r.enabled === false ? "Resume" : "Pause"}</button>
        <button onclick="deleteReminder('${r.id}')" class="text-xs text-slate-400 underline">Delete</button>
      </div>
    </div>`).join("")
    : `<p class="text-xs text-slate-500">No reminders. Reminders are user-configured and <strong>in-app only</strong> — they never deliver when this app is closed.</p>`;
  $("#storage-note").textContent =
    `Data on this device only: ${lastUsage.length} doses, ${lastSymptoms.length} symptoms, ${lastObservations.length} observations for ${profile ? profile.name : "—"}, stored in this browser's IndexedDB. Clearing your browser's site data for this app deletes every record permanently — use Export to keep a backup copy.`;
}

async function createProfile(ev) {
  ev.preventDefault();
  const form = ev.target;
  const nameEl = form.elements.pname, ageEl = form.elements.page;
  const name = nameEl.value.trim();
  if (!name) { toast("Profile needs a name", true); return; }
  const p = await Store.createProfile(name, ageEl ? ageEl.value : "", "");
  await switchProfile(p.id);
  nameEl.value = ""; if (ageEl) ageEl.value = "";
  $("#first-run").classList.add("hidden");
  toast(`✓ Profile "${name}" created`);
  await loadAll();
}
async function deleteProfile() {
  if (!profile) return;
  if (!confirm(`Delete profile "${profile.name}" and ALL of its records permanently from this device?`)) return;
  await Store.deleteProfile(profile.id);
  profile = null;
  const profiles = await Store.profiles();
  await switchProfile(profiles[0] ? profiles[0].id : null);
  if (!profile) $("#first-run").classList.remove("hidden");
  toast("Profile deleted");
  await loadAll();
}

// ---------------- EXPORT / IMPORT ----------------
function exportData() {
  // Full export: every profile and all of its records, for backup/restore.
  return Store.profiles().then(async profiles => {
    const data = {
      app: "peptide-safety-tracker",
      schema: 1,
      exportedAt: nowISO(),
      disclaimer: "User-entered journal data. Not medical advice; not verified by this app. Keep private.",
      profiles: [],
    };
    for (const p of profiles) {
      data.profiles.push({
        profile: p,
        goals: (await Store.goalsFor(p.id)).goalKeys || [],
        usage: (await Store.byProfile("usage", p.id)).map(r => ({ ...r })),
        symptoms: (await Store.byProfile("symptoms", p.id)).map(r => ({ ...r })),
        observations: (await Store.byProfile("observations", p.id)).map(r => ({ ...r })),
        reminders: (await Store.byProfile("reminders", p.id)).map(r => ({ ...r })),
      });
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "peptide-log-export-" + new Date().toISOString().slice(0, 10) + ".json";
    a.click();
    URL.revokeObjectURL(a.href);
    toast("✓ Export downloaded — keep the file private");
    return data;
  });
}

function validateExport(data) {
  // Returns {ok, errors[], counts} — strict enough to refuse junk, loose
  // enough to accept legit exports from any version with schema 1.
  const errors = [];
  if (!data || typeof data !== "object") return { ok: false, errors: ["Not an object"], counts: null };
  if (data.app !== "peptide-safety-tracker") errors.push("Not an export of this app (wrong app id).");
  if (data.schema !== 1) errors.push("Unknown export schema version.");
  if (!Array.isArray(data.profiles) || !data.profiles.length) errors.push("No profiles in export.");
  const counts = { profiles: 0, usage: 0, symptoms: 0, observations: 0, reminders: 0 };
  if (data.profiles && typeof data.profiles[Symbol.iterator] === "function") {
    for (const block of data.profiles) {
      if (!block || !block.profile || !block.profile.id || !block.profile.name) {
        errors.push("A profile block is missing its id or name."); continue;
      }
      counts.profiles++;
      for (const [key, store, check] of [
        ["usage", "usage", r => Number(r.amount) > 0 && UNITS.includes(r.unit)],
        ["symptoms", "symptoms", r => r.severity >= 1 && r.severity <= 5],
        ["observations", "observations", () => true],
        ["reminders", "reminders", r => /^[0-2][0-9]:[0-5][0-9]$/.test(r.timeOfDay)],
      ]) {
        if (!Array.isArray(block[key])) { errors.push(`${key} list missing for ${block.profile.name}.`); continue; }
        for (const r of block[key]) {
          if (!r || !r.id) { errors.push(`${key}: record without id.`); continue; }
          if (!check(r)) errors.push(`${key} (${r.id}): invalid ${key === "usage" ? "amount/unit" : key === "symptoms" ? "severity" : "value"} — record skipped on import.`);
          else counts[key]++;
        }
      }
      if (Array.isArray(block.goals)) {
        block.goals = block.goals.filter(k => GOALS[k]);
      }
    }
  }
  return { ok: errors.filter(e => e.startsWith("Not") || e.startsWith("Unknown") || e.startsWith("No profiles") || e.includes("missing")).length === 0,
           errors, counts };
}

async function importFile(file) {
  let text;
  try { text = await file.text(); }
  catch { toast("Could not read the file", true); return; }
  let data;
  try { data = JSON.parse(text); }
  catch { showImportPreview({ ok: false, errors: ["The file is not valid JSON."], counts: null }); return; }
  const v = validateExport(data);
  if (!v.ok) { showImportPreview(v); return; }
  // preview with counts + mode choice
  showImportPreview(v, data);
}

function showImportPreview(v, data) {
  const box = $("#import-preview");
  if (!v.ok) {
    box.classList.remove("hidden");
    box.innerHTML = `<div class="bg-red-950/40 border border-red-800 rounded-xl p-4 space-y-1">
      <p class="text-sm font-bold text-red-300">Import refused — validation failed</p>
      <ul class="text-xs text-red-200 list-disc pl-4">${v.errors.map(e => `<li>${esc(e)}</li>`).join("")}</ul></div>`;
    return;
  }
  box.classList.remove("hidden");
  box.innerHTML = `<div class="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-2">
    <p class="text-sm font-bold">Import preview</p>
    <p class="text-xs text-slate-300">${v.counts.profiles} profile(s): ${v.counts.usage} doses, ${v.counts.symptoms} symptoms, ${v.counts.observations} observations, ${v.counts.reminders} reminders.</p>
    ${v.errors.length ? `<p class="text-xs text-amber-300">${v.errors.length} record(s) failed validation and will be skipped.</p>` : ""}
    <p class="text-xs text-slate-400"><strong>Merge</strong> keeps what is already on this device and adds the file's records.
      <strong>Replace</strong> deletes everything on this device first — use only when restoring a backup.</p>
    <div class="flex gap-2 pt-1">
      <button onclick="runImport('merge')" class="btn !py-2 !text-xs">Merge into this device</button>
      <button onclick="runImport('replace')" class="btn2 !py-2 !text-xs">Replace everything</button>
      <button onclick="document.getElementById('import-preview').classList.add('hidden')" class="text-xs text-slate-400 underline self-center">Cancel</button>
    </div></div>`;
  box.dataset.payload = JSON.stringify(data);
}

async function runImport(mode) {
  const box = $("#import-preview");
  const data = JSON.parse(box.dataset.payload || "null");
  if (!data) return;
  const v = validateExport(data);
  if (mode === "replace") {
    if (!confirm("Replace EVERYTHING on this device with the export file? Current records will be permanently deleted.")) return;
    await Store.wipeAllData();
  }
  let skipped = 0, added = 0;
  const existing = new Set();
  if (mode === "merge") {
    for (const store of ["profiles", "usage", "symptoms", "observations", "reminders"]) {
      for (const r of await Store.getAll(store)) existing.add(store + ":" + r.id);
    }
  }
  for (const block of data.profiles) {
    if (mode === "merge" && existing.has("profiles:" + block.profile.id)) {
      // profile exists; still import its records (dedup by id below)
    } else {
      await Store.put("profiles", block.profile);
    }
    await Store.put("goals", { id: block.profile.id, goalKeys: block.goals || [] });
    for (const [key, store, check] of [
      ["usage", "usage", r => Number(r.amount) > 0 && UNITS.includes(r.unit)],
      ["symptoms", "symptoms", r => r.severity >= 1 && r.severity <= 5],
      ["observations", "observations", () => true],
      ["reminders", "reminders", r => /^[0-2][0-9]:[0-5][0-9]$/.test(r.timeOfDay)],
    ]) {
      for (const r of block[key] || []) {
        const keyId = store + ":" + r.id;
        if (mode === "merge" && existing.has(keyId)) continue;
        if (!check(r)) { skipped++; continue; }
        await Store.put(store, { ...r, profileId: block.profile.id });
        added++;
      }
    }
  }
  box.classList.add("hidden");
  $("#import-file").value = "";
  toast(`✓ Import complete — ${added} record(s) added${skipped ? ", " + skipped + " skipped as invalid" : ""}`);
  const first = (await Store.profiles())[0];
  await switchProfile(first ? first.id : null);
  if (!profile) $("#first-run").classList.remove("hidden");
  await loadAll();
}

// ---------------- product picker ----------------
function attachPicker(inputId, listId, onPick) {
  const input = $(inputId), dd = $(listId);
  let items = [];
  const render = () => {
    const q = input.value.trim().toLowerCase();
    const base = q ? Object.values(catalogIndex).filter(c => c.name.toLowerCase().includes(q)) : Object.values(catalogIndex);
    const seen = new Set();
    items = base.filter(c => !seen.has(c.name) && seen.add(c.name)).slice(0, 8);
    dd.innerHTML = items.length
      ? items.map(c => `<button type="button" class="w-full text-left px-3 py-2 hover:bg-slate-800 text-sm" onclick="pick_${listId.replace(/[-#]/g, "")}('${esc(c.name).replace(/'/g, "\\'")}')">${esc(c.name)}</button>`).join("")
      : `<p class="px-3 py-2 text-xs text-slate-500">No catalog match — you can still save the name you typed.</p>`;
    dd.classList.remove("hidden");
  };
  window["pick_" + listId.replace(/[-#]/g, "")] = (name) => {
    input.value = name;
    dd.classList.add("hidden");
    if (onPick) onPick(name);
  };
  // Keep focus in the input while tapping an option so blur can't hide the list first.
  dd.addEventListener("mousedown", ev => ev.preventDefault());
  input.addEventListener("focus", render);
  input.addEventListener("input", render);
  input.addEventListener("blur", () => setTimeout(() => dd.classList.add("hidden"), 120));
  document.addEventListener("click", ev => {
    if (!ev.target.closest || !ev.target.closest(".picker-wrap")) dd.classList.add("hidden");
  });
}

// ---------------- tabs ----------------
function gotoTab(name) {
  for (const t of ["today", "history", "catalog", "settings"]) {
    $("#sec-" + t).classList.toggle("hidden", t !== name);
    $("#nav-" + t).classList.toggle("text-emerald-400", t === name);
    $("#nav-" + t).classList.toggle("text-slate-500", t !== name);
  }
  window.scrollTo(0, 0);
}

document.addEventListener("DOMContentLoaded", () => {
  init();
  attachPicker("#u-name", "#u-name-dd");
  attachPicker("#r-name", "#r-name-dd");
  $("#hist-q").addEventListener("input", renderHistory);
  $("#hist-type").addEventListener("change", renderHistory);
  $("#cat-q").addEventListener("input", renderCatalog);
  $("#import-file").addEventListener("change", ev => {
    if (ev.target.files[0]) importFile(ev.target.files[0]);
  });
  $("#profile-select").addEventListener("change", ev => switchProfile(ev.target.value));
});
