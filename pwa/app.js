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
const esc = (s) => { const d = document.createElement("div"); d.textContent = s ?? "";
  // quotes are escaped too so the result is safe inside attributes
  return d.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;"); };
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
const localDTtoDay = (d) => {
  const off = d.getTimezoneOffset();
  return new Date(d - off * 60000).toISOString().slice(0, 10);
};
function clearDateFilter() {
  $("#hist-from").value = ""; $("#hist-to").value = "";
  renderHistory();
}

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
    // Controlled updates: the new worker stays "waiting" until the user
    // taps "Reload & update" — an unfinished form is never interrupted.
    navigator.serviceWorker.register("./sw.js").then(reg => {
      // An update may already be waiting from an earlier session — detect it.
      if (reg.waiting && navigator.serviceWorker.controller) {
        $("#update-banner").classList.remove("hidden");
      }
      // Detect a newly discovered update.
      reg.addEventListener("updatefound", () => {
        const nw = reg.installing;
        if (!nw) return;
        nw.addEventListener("statechange", () => {
          if (nw.state === "installed" && navigator.serviceWorker.controller) {
            $("#update-banner").classList.remove("hidden");
          }
        });
      });
    }).catch(() => {});
    // Reload exactly once, after the waiting worker has taken over.
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      reloadedFlag = true;
      location.reload();
    });
  }
  await loadAll();
  window.addEventListener("online", () => $("#offline-badge").classList.add("hidden"));
  window.addEventListener("offline", () => $("#offline-badge").classList.remove("hidden"));
  if (!navigator.onLine) $("#offline-badge").classList.remove("hidden");
  restoreDraft();
  // Surface a blocked DB upgrade (another tab holds an old connection).
  Store.onBlocked = (err) =>
    toast(err && err.message ? err.message :
      "A data update is waiting — close this app in other tabs, then reload.", true);
}

// ---- unsaved-form draft preservation for updates ----
// Before reloading for an update, capture anything typed into an open
// sheet (log / symptom / observation forms, appointment summary) so the
// user can cancel the update or keep their draft.
function collectDraft() {
  const draft = {};
  const grab = (id) => { const el = $(id); return el ? el.value : ""; };
  if (!$("#log-sheet").classList.contains("hidden")) {
    draft.sheet = "log";
    draft.data = { name: grab("#u-name"), amount: grab("#u-amount"),
      unit: grab("#u-unit"), when: grab("#u-when"), notes: grab("#u-notes") };
    draft.title = $("#log-sheet-title").textContent;
  } else if (!$("#symptom-sheet").classList.contains("hidden")) {
    draft.sheet = "symptom";
    draft.data = { name: grab("#s-name"), desc: grab("#s-desc"),
      severity: grab("#s-severity") };
  } else if (!$("#observation-sheet").classList.contains("hidden")) {
    draft.sheet = "observation";
    draft.data = { when: grab("#o-when"), notes: grab("#o-notes"),
      goals: collectGoalData() };
  } else if (!$("#summary-sheet").classList.contains("hidden")) {
    draft.sheet = "summary";
    draft.data = { from: grab("#sum-from"), to: grab("#sum-to"),
      includeNotes: $("#sum-notes").checked, questions: grab("#sum-questions") };
  }
  // dynamic observation goal fields (.gf inputs) are inside the
  // observation sheet and captured via collectGoalData() above.
  return draft.sheet ? draft : null;
}

function draftHasContent(d) {
  if (!d) return false;
  const v = d.data || {};
  return Object.values(v).some(x =>
    typeof x === "string" ? x.trim() !== "" : !!x);
}

function captureDraftForUpdate() {
  const d = collectDraft();
  if (!d || !draftHasContent(d)) return true;   // nothing to lose
  try { sessionStorage.setItem("pwa-draft", JSON.stringify(d)); } catch (e) {}
  return confirm(
    "An update is ready. You have an unfinished entry open.\n\n" +
    "\"OK\" saves your draft and reloads (it will be restored after the " +
    "update). \"Cancel\" keeps working without updating now.");
}

function applyUpdate() {
  // Only runs when the user taps "Reload & update" — never automatically.
  if (!captureDraftForUpdate()) { dismissUpdate(); return; }
  const reg = navigator.serviceWorker && navigator.serviceWorker.controller;
  const banner = $("#update-banner");
  banner.querySelector("p").textContent = "Updating — reloading…";
  if (reg) reg.postMessage({ type: "ACCEPT_UPDATE" });
  // controllerchange reloads once the new worker takes over; if there is
  // no waiting worker (banner stale), reload directly after a short grace
  // period instead of hanging forever.
  setTimeout(() => { if (!reloadedFlag) location.reload(); }, 1500);
}
let reloadedFlag = false;
function dismissUpdate() { $("#update-banner").classList.add("hidden"); }

// Restore a draft saved before an update reload. Runs after init so the
// sheets exist; only restores what the user had typed, nothing else.
function restoreDraft() {
  let raw = null;
  try { raw = sessionStorage.getItem("pwa-draft"); } catch (e) {}
  if (!raw) return;
  try { sessionStorage.removeItem("pwa-draft"); } catch (e) {}
  let d;
  try { d = JSON.parse(raw); } catch (e) { return; }
  if (!d || !d.sheet || !d.data) return;
  setTimeout(() => {
    if (d.sheet === "log") {
      openLogSheet(null);
      $("#log-sheet-title").textContent = d.title || "Log a dose";
      $("#u-name").value = d.data.name || "";
      $("#u-amount").value = d.data.amount || "";
      $("#u-unit").value = UNITS.includes(d.data.unit) ? d.data.unit : "";
      $("#u-when").value = d.data.when || "";
      $("#u-notes").value = d.data.notes || "";
      lastLockedProduct = d.data.name || "";
      showUnitHint(d.data.name, d.data.unit);
      toast("Your unfinished entry was restored after the update.");
    } else if (d.sheet === "symptom") {
      openSymptomSheet();
      $("#s-name").value = d.data.name || "";
      $("#s-desc").value = d.data.desc || "";
      $("#s-severity").value = ["1","2","3","4","5"].includes(d.data.severity)
        ? d.data.severity : "3";
      toast("Your unfinished symptom entry was restored after the update.");
    } else if (d.sheet === "observation") {
      openObservationSheet();
      $("#o-when").value = d.data.when || "";
      $("#o-notes").value = d.data.notes || "";
      if (d.data.goals) {
        for (const [k, v] of Object.entries(d.data.goals)) {
          const el = document.querySelector(
            `#observation-fields .gf[data-gkey="${CSS.escape(k)}"]`);
          if (el) el.value = v;
        }
      }
      toast("Your unfinished observation was restored after the update.");
    } else if (d.sheet === "summary") {
      openSummarySheet();
      $("#sum-from").value = d.data.from || "";
      $("#sum-to").value = d.data.to || "";
      $("#sum-notes").checked = !!d.data.includeNotes;
      $("#sum-questions").value = d.data.questions || "";
      renderSummaryPreview();
      toast("Your appointment summary draft was restored after the update.");
    }
  }, 400);
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
        <div class="text-right shrink-0"><span class="text-xs text-slate-500">${fmtWhen(u.takenAt)}</span>
          <button data-act="log-again" data-id="${esc(u.id)}" class="block text-xs text-emerald-400 underline">Log again</button></div>
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
  $("#u-unit").value = "";                        // no silent default unit
  $("#u-unit-hint").classList.add("hidden");
  if (editingUsageId) {
    const e = lastUsage.find(x => x.id === editingUsageId);
    if (e) {
      $("#u-name").value = e.peptideName;
      $("#u-amount").value = e.amount;
      $("#u-unit").value = e.unit;
      $("#u-when").value = toLocalInput(e.takenAt);
      $("#u-notes").value = e.notes || "";
      showUnitHint(e.peptideName, e.unit);
    }
  } else {
    $("#u-when").value = localDT();
  }
  clearErrors(form);
  lastLockedProduct = $("#u-name").value.trim();  // lock the current product
  $("#log-sheet").classList.remove("hidden");
  setTimeout(() => $("#u-name").focus(), 60);
}

// ---- explicit units (backlog: "Now") ----
// New product entries start with "Choose unit" — no unit is silently
// selected. A unit previously confirmed for the same product in the same
// profile is pre-selected and clearly shown before saving. Changing the
// product name never carries over an unrelated unit.
let lastLockedProduct = "";

function showUnitHint(name, unit) {
  const hint = $("#u-unit-hint");
  if (name && unit) {
    hint.textContent = `Unit shown from your previous "${name}" entry: ${unit} — confirm before saving.`;
    hint.classList.remove("hidden");
  } else hint.classList.add("hidden");
}

// Monotonic token guarding the async remembered-unit lookup: a slow result
// for an earlier product must never overwrite a newer state (e.g. the user
// cleared the field or switched products while the lookup was in flight).
let unitLookupToken = 0;

async function onProductChanged() {
  const form = $("#log-sheet form");
  if (!form || $("#log-sheet").classList.contains("hidden")) return;
  const name = $("#u-name").value.trim();
  if (name.toLowerCase() === lastLockedProduct.toLowerCase()) return;
  lastLockedProduct = name;
  const token = ++unitLookupToken;      // profile/product/sheet-instance token
  const forProfile = profile.id;
  const sheetEpoch = form.dataset.idem;
  if (editingUsageId) return;   // corrections keep the entry's original unit
  // changing products does not carry over an unrelated unit
  $("#u-unit").value = "";
  $("#u-unit-hint").classList.add("hidden");
  if (name) {
    const remembered = await Store.rememberedUnit(forProfile, name);
    // apply ONLY if nothing newer happened: same open sheet, same product
    if (token !== unitLookupToken ||
        $("#log-sheet").classList.contains("hidden") ||
        form.dataset.idem !== sheetEpoch ||
        $("#u-name").value.trim() !== name) {
      return;                    // stale result — discard it
    }
    if (remembered) {
      $("#u-unit").value = remembered;
      showUnitHint(name, remembered);
    }
  }
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
// Repeated-tap guard: a double-tap on Save must not create two records.
// Returns a release() function — called when the save finishes (or when
// validation fails, so a corrected retry is never swallowed).
function guardBusy(submit) {
  if (submit.dataset.busy) return null;
  submit.dataset.busy = "1";
  submit.disabled = true;
  return () => { delete submit.dataset.busy; submit.disabled = false; };
}
function formError(sel, msg, input) {
  const box = $(sel);
  if (box) box.textContent = msg;
  if (input) input.classList.add("invalid");
}

// ---------------- submissions ----------------
async function logUsage(ev) {
  ev.preventDefault();
  const form = ev.target, submit = $("#u-submit");
  clearErrors(form);
  const name = $("#u-name").value.trim();
  const amount = parseFloat($("#u-amount").value);
  const unit = $("#u-unit").value;
  if (!name) { formError("#u-error", "Enter a product or peptide name.", $("#u-name")); return; }
  if (!(amount > 0)) { formError("#u-error", "Amount must be a number greater than 0.", $("#u-amount")); return; }
  if (!unit) { formError("#u-error", "Choose a unit — every amount is saved with an explicit unit (mcg, mg, IU, units, or mL)."); return; }
  if (!UNITS.includes(unit)) { formError("#u-error", "Explicit unit required (mcg, mg, IU, units, mL)."); return; }
  const when = $("#u-when").value;
  const takenAt = when ? new Date(when).toISOString() : nowISO();
  const notes = $("#u-notes").value;
  // guard begins here — after validation, so a corrected retry always works
  const release = guardBusy(submit);
  if (!release) return;
  try {
    await doSaveUsage(form, { name, amount, unit, takenAt, notes });
  } finally {
    release();
  }
}

async function doSaveUsage(form, { name, amount, unit, takenAt, notes }) {

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
  // the unit was explicitly chosen and saved — remember it for this
  // product in this profile only
  await Store.rememberUnit(profile.id, name, unit);
  delete form.dataset.override;
  form.reset();
  lastLockedProduct = "";
  $("#u-when").value = localDT();
  closeLogSheet();
  toast(`✓ Saved ${name} (${amount} ${unit}) for ${fmtWhen(takenAt)}`);
  await loadAll();
}

async function logSymptom(ev) {
  ev.preventDefault();
  const submit = document.querySelector('#symptom-sheet button.btn');
  const form = ev.target;
  clearErrors(form);
  const name = $("#s-name").value.trim();
  const description = $("#s-desc").value.trim();
  const severity = parseInt($("#s-severity").value, 10);
  if (!name) { formError("#s-error", "Name the symptom (e.g., 'headache').", $("#s-name")); return; }
  if (!description) { formError("#s-error", "Describe what you felt.", $("#s-desc")); return; }
  if (!(severity >= 1 && severity <= 5)) { formError("#s-error", "Severity must be 1–5."); return; }
  const release = guardBusy(submit);
  if (!release) return;
  try {
    await Store.put("symptoms", { id: uid(), profileId: profile.id, peptideName: name,
      severity, description, loggedAt: nowISO() });
  } finally { release(); }
  form.reset(); $("#s-severity").value = "3";
  closeSymptomSheet();
  toast(`✓ Symptom logged (${severity}/5)`);
  await loadAll();
}

async function logObservation(ev) {
  ev.preventDefault();
  const submit = document.querySelector('#observation-sheet button.btn');
  const form = ev.target;
  clearErrors(form);
  const when = $("#o-when").value;
  const notes = $("#o-notes").value;
  const goalData = collectGoalData();
  if (!notes && !goalData) {
    formError("#o-error", "Add a note or at least one measurement."); return;
  }
  const release = guardBusy(submit);
  if (!release) return;
  try {
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
  } finally { release(); }
  closeObservationSheet();
  toast("✓ Observation saved");
  await loadAll();
}

// ---- repeat logging ("Log again", backlog: "Now") ----
// Opens a reviewable pre-filled form — never creates a record immediately.
// The new entry's time is NOW (the prior entry's time stays visible for
// comparison); amount and unit are pre-filled but must be reviewed and
// confirmed by saving. Personal notes are NOT copied.
function logAgain(entryId) {
  const e = lastUsage.find(x => x.id === entryId);
  if (!e) return;
  openLogSheet(null);
  $("#log-sheet-title").textContent = `Log again — ${e.peptideName}`;
  $("#u-name").value = e.peptideName;
  $("#u-amount").value = e.amount;
  $("#u-unit").value = e.unit;
  $("#u-when").value = localDT();   // new time, never the prior entry's time
  lastLockedProduct = e.peptideName;
  showUnitHint(e.peptideName, e.unit);
  $("#u-notes").value = "";         // notes are not copied without review
  formError("#u-error",
    `Review before saving: this prefills your previous ${esc(e.peptideName)} entry (${esc(e.amount)} ${esc(e.unit)}, ${fmtWhen(e.takenAt)}). The new time is set to now.`);
  setTimeout(() => $("#u-amount").focus(), 60);
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
  const from = $("#hist-from")?.value;   // inclusive, local date
  const to = $("#hist-to")?.value;       // inclusive, local date
  const rows = [];
  const inRange = (iso) => {
    if (!iso) return true;
    const d = new Date(iso);
    if (isNaN(d)) return true;
    const day = localDTtoDay(d);
    if (from && day < from) return false;
    if (to && day > to) return false;
    return true;
  };
  if (type === "all" || type === "dose") lastUsage.forEach(u => inRange(u.takenAt) && rows.push({ kind: "dose", when: u.takenAt, u }));
  if (type === "all" || type === "symptom") lastSymptoms.forEach(s => inRange(s.loggedAt) && rows.push({ kind: "symptom", when: s.loggedAt, s }));
  if (type === "all" || type === "observation") lastObservations.forEach(o => inRange(o.takenAt) && rows.push({ kind: "observation", when: o.takenAt, o }));
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
            <button data-act="log-again" data-id="${esc(u.id)}" class="text-xs text-emerald-400 underline">Log again</button> ·
            <button data-act="correct-dose" data-id="${esc(u.id)}" class="text-xs text-emerald-400 underline">Correct</button></div>
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
          <button data-act="correct-obs" data-id="${esc(o.id)}" class="text-xs text-sky-400 underline">Correct</button></div>
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
      <p class="text-xs text-slate-400">Links only — the app never interprets results and never rates a brand. Verify licensure, prescription status, and the exact product yourself. Approval wording in this app is ingredient-level ("approved products exist"); whether one specific product is approved is checked per exact product in Drugs@FDA — DailyMed shows labeling only and also lists unapproved products. These links include the product name you're checking in their address.</p>
      <ul class="text-xs space-y-1 list-disc pl-4">
        <li><a class="text-emerald-400 underline" target="_blank" rel="noopener" href="https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=${q}">DailyMed label search</a></li>
        <li><a class="text-emerald-400 underline" target="_blank" rel="noopener" href="https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?fuseaction=Search.SearchResults&Query.Name=${q}">Drugs@FDA — check approval per exact product</a></li>
        <li><a class="text-emerald-400 underline" target="_blank" rel="noopener" href="https://open.fda.gov/data/drug/">openFDA drug records</a></li>
        <li><a class="text-emerald-400 underline" target="_blank" rel="noopener" href="https://www.fda.gov/drugs/human-drug-compounding">FDA human drug compounding</a></li>
        <li><a class="text-emerald-400 underline" target="_blank" rel="noopener" href="https://www.fda.gov/consumers/buying-medicine-online">FDA: Buying Medicine Online</a></li>
      </ul>
    </div>`;
}

// ---------------- appointment summary (backlog standout) ----------------
// Builds a reviewable, printable summary of a chosen date range. Shows the
// user exactly what will be shared BEFORE anything is produced; private
// notes are excluded by default with an explicit opt-in. It is labeled as
// user-entered and possibly incomplete, and makes no cause/effect or
// treatment claims. Nothing is sent anywhere automatically.
const SUMMARY_DISCLAIMER =
  "Summary of what was typed into this app for this profile during the " +
  "selected period. User-entered and possibly incomplete — the app does not " +
  "verify any of it. This is not medical advice and implies nothing about " +
  "cause, effect, or treatment effectiveness. Missing data means nothing was " +
  "recorded, not that nothing happened.";

function openSummarySheet() {
  const today = localDTtoDay(new Date());
  $("#sum-from").value = localDTtoDay(new Date(Date.now() - 30 * 86400000));
  $("#sum-to").value = today;
  $("#sum-notes").checked = false;
  $("#sum-questions").value = "";
  renderSummaryPreview();
  $("#summary-sheet").classList.remove("hidden");
}
function closeSummarySheet() { $("#summary-sheet").classList.add("hidden"); }

function summaryData() {
  const from = $("#sum-from").value;
  const to = $("#sum-to").value;
  const includeNotes = $("#sum-notes").checked;
  // dates entered as local calendar days; entries compared by their LOCAL
  // calendar day (consistent with the History date filters)
  const reversed = !!from && !!to && from > to;
  const inRange = (iso) => {
    if (!iso) return false;
    const day = localDTtoDay(new Date(iso));
    return (!from || day >= from) && (!to || day <= to);
  };
  const usage = reversed ? [] : lastUsage.filter(u => inRange(u.takenAt));
  const symptoms = reversed ? [] : lastSymptoms.filter(s => inRange(s.loggedAt));
  const observations = reversed ? [] : lastObservations.filter(o => inRange(o.takenAt));
  const questions = $("#sum-questions").value.trim();
  return { from, to, includeNotes, usage, symptoms, observations, questions, reversed };
}

function summaryRangeError(d) {
  if (d.reversed) {
    return "The From date is after the To date — swap them, then review again.";
  }
  if (!d.from && !d.to) {
    return "Choose at least one date so the summary matches a clear period.";
  }
  return null;
}

const SUMMARY_SENSITIVITY =
  "Sensitive: this summary can contain health information. Keep it private " +
  "— share it only with the clinician or people you choose.";

function summaryHtmlText(d) {
  const esc2 = esc;
  let out = "";
  // products: grouped by name + unit, amounts listed as recorded
  const groups = {};
  for (const u of d.usage) {
    const k = u.peptideName + "|" + u.unit;
    (groups[k] = groups[k] || { name: u.peptideName, unit: u.unit, items: [] }).items.push(u);
  }
  const productLines = Object.values(groups).map(g =>
    `<li><strong>${esc2(g.name)}</strong> (${esc2(g.unit)}): ` +
    g.items.map(i => `${esc2(i.amount)}${d.includeNotes && i.notes ? " — " + esc2(i.notes) : ""}`).join(", ")
    + ` <span class="muted">— ${g.items.length} entr${g.items.length === 1 ? "y" : "ies"} recorded during this period</span></li>`);
  const symptomLines = d.symptoms.map(s =>
    `<li>${fmtWhen(s.loggedAt)} — <strong>${esc2(s.peptideName)}</strong>, severity ${s.severity}/5: ${esc2(s.description)}</li>`);
  const obsLines = d.observations.map(o => {
    const fields = o.goalData
      ? Object.entries(o.goalData).map(([k, v]) => `${esc2(k)}: ${esc2(v)}`).join("; ")
      : "";
    return `<li>${fmtWhen(o.takenAt)}${fields ? " — " + fields : ""}` +
      (d.includeNotes && o.notes ? ` — ${esc2(o.notes)}` : "") + `</li>`;
  });
  if (productLines.length) out += `<h2>Products recorded</h2><ul>${productLines.join("")}</ul>`;
  else out += `<h2>Products recorded</h2><p class="muted">No doses recorded during this period.</p>`;
  if (symptomLines.length) out += `<h2>Symptoms recorded</h2><ul>${symptomLines.join("")}</ul>`;
  else out += `<h2>Symptoms recorded</h2><p class="muted">No symptoms recorded during this period.</p>`;
  if (obsLines.length) out += `<h2>Measurements and observations</h2><ul>${obsLines.join("")}</ul>`;
  if (d.questions) out += `<h2>Questions I want to ask</h2><ul>${d.questions.split(/\n+/).map(q => `<li>${esc2(q)}</li>`).join("")}</ul>`;
  if (!d.includeNotes) out += `<p class="muted">Private notes were excluded by choice (option not selected).</p>`;
  out += `<p class="muted">${esc(SUMMARY_SENSITIVITY)}</p>`;
  return out;
}

function renderSummaryPreview() {
  const d = summaryData();
  const rangeError = summaryRangeError(d);
  if (rangeError) {
    $("#sum-preview").innerHTML = `
      <div class="bg-amber-950/40 border border-amber-900/60 rounded-xl p-4">
        <p class="text-xs text-amber-200">${esc(rangeError)}</p>
      </div>`;
    return;
  }
  const count = d.usage.length + d.symptoms.length + d.observations.length;
  $("#sum-preview").innerHTML = `
    <div class="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-1 text-sm max-h-72 overflow-y-auto">
      <p class="text-xs text-slate-400">${count} entr${count === 1 ? "y" : "ies"} selected · ${esc(d.from)} → ${esc(d.to)} · notes ${d.includeNotes ? "included" : "excluded"}</p>
      ${summaryHtmlText(d).replace(/<h2>/g, '<h2 class="text-sm font-bold pt-2">').replace(/<ul>/g, '<ul class="list-disc pl-4 space-y-0.5 text-xs text-slate-300">').replace(/<p class="muted">/g, '<p class="text-xs text-slate-500">')}
    </div>`;
}

function summaryDocHtml(d) {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Appointment summary</title>
  <style>
    body{font-family:system-ui,sans-serif;color:#111;margin:2rem;max-width:46rem;line-height:1.45}
    h1{font-size:1.3rem} h2{font-size:1rem;margin:1.1rem 0 .3rem;border-bottom:1px solid #ddd;padding-bottom:.2rem}
    ul{padding-left:1.2rem} li{margin:.15rem 0}
    .muted{color:#666;font-size:.85rem}
    .box{border:1px solid #ccc;padding:.6rem .8rem;border-radius:.4rem;font-size:.85rem;margin:.8rem 0}
    @media print{ body{margin:1rem} }
  </style></head><body>
  <h1>Appointment summary — ${esc(d.from || "start")} to ${esc(d.to || "today")}</h1>
  <p>Profile: <strong>${esc(profile ? profile.name : "")}</strong> · Generated ${fmtWhen(nowISO())} by the Peptide Safety Tracker.</p>
  <div class="box"><strong>What this is:</strong> ${SUMMARY_DISCLAIMER}</div>
  ${summaryHtmlText(d)}
  <p class="muted">End of summary.</p>
  </body></html>`;
}

function printSummary() {
  const d = summaryData();
  const rangeError = summaryRangeError(d);
  if (rangeError) { toast(rangeError, true); return; }
  const w = window.open("", "_blank");
  if (!w) { toast("Allow pop-ups to print the summary", true); return; }
  w.document.write(summaryDocHtml(d));
  w.document.close();
  setTimeout(() => { try { w.focus(); w.print(); } catch (e) {} }, 300);
}

function downloadSummary() {
  const d = summaryData();
  const rangeError = summaryRangeError(d);
  if (rangeError) { toast(rangeError, true); return; }
  const blob = new Blob([summaryDocHtml(d)], { type: "text/html" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "appointment-summary-" + (d.from || "start") + "-to-" + (d.to || "today") + ".html";
  a.click();
  URL.revokeObjectURL(a.href);
  toast("Summary downloaded — nothing was sent anywhere");
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
        <button data-act="toggle-reminder" data-id="${esc(r.id)}" class="text-xs text-emerald-400 underline">${r.enabled === false ? "Resume" : "Pause"}</button>
        <button data-act="delete-reminder" data-id="${esc(r.id)}" class="text-xs text-slate-400 underline">Delete</button>
      </div>
    </div>`).join("")
    : `<p class="text-xs text-slate-500">No reminders. Reminders are user-configured and <strong>in-app only</strong> — they never deliver when this app is closed.</p>`;
  $("#storage-note").textContent =
    `Data on this device only: ${lastUsage.length} doses, ${lastSymptoms.length} symptoms, ${lastObservations.length} observations for ${profile ? profile.name : "—"}, stored in this browser's IndexedDB. Clearing your browser's site data for this app deletes every record permanently — use Export to keep a backup copy.`;
  $("#app-version").textContent = APP_VERSION;
  // last backup time + dismissible reminder (dismissal lasts 7 days)
  const last = await Store.getMeta("lastBackupAt");
  const dismissedAt = await Store.getMeta("backupReminderDismissedAt");
  $("#last-backup").textContent = last
    ? `Last export initiated: ${fmtWhen(last)} — the app cannot see the file, so verify the downloaded copy opens and keep it somewhere safe.`
    : "No backup made yet on this device.";
  const daysSince = last ? Math.floor((Date.now() - new Date(last)) / 86400000) : null;
  const dismissed = dismissedAt && (Date.now() - new Date(dismissedAt)) < 7 * 86400000;
  const showReminder = !dismissed && (daysSince === null || daysSince >= 7);
  $("#backup-reminder").classList.toggle("hidden", !showReminder);
  $("#backup-dismiss").classList.toggle("hidden", !showReminder);
  if (showReminder) {
    $("#backup-reminder").textContent = daysSince === null
      ? "Reminder: make a backup (Export) so a browser reset can't take your records with it. After exporting, verify the downloaded file opens."
      : `It has been ${daysSince} days since your last export — consider downloading a fresh copy and verifying it opens.`;
  }
}

async function dismissBackupReminder() {
  await Store.setMeta("backupReminderDismissedAt", nowISO());
  $("#backup-reminder").classList.add("hidden");
}

const APP_VERSION = "pwa 0.2.0-beta";

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
      schema: 2,   // 2 = includes remembered productUnits per profile
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
        productUnits: (await Store.getAll("productUnits"))
          .filter(u => u.profileId === p.id).map(u => ({ ...u })),
      });
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "peptide-log-export-" + new Date().toISOString().slice(0, 10) + ".json";
    a.click();
    URL.revokeObjectURL(a.href);
    await Store.setMeta("lastBackupAt", nowISO());
    toast("✓ Backup file downloaded — verify it opens, then keep it private");
    await renderSettings();
    return data;
  });
}

const IMPORT_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;
const IMPORT_LIMITS = {
  profiles: 50, usage: 5000, symptoms: 5000, observations: 5000,
  reminders: 500, productUnits: 2000,
};
const IMPORT_TOTAL_LIMIT = 12000;

function validISODate(v) {
  return typeof v === "string" && v.length <= 40 &&
    !Number.isNaN(new Date(v).getTime());
}

function validateExport(data) {
  // Returns {ok, errors[], counts} — strict enough to refuse junk and
  // malicious files, loose enough to accept legit exports from this app
  // (schema 1 and 2). Everything is validated BEFORE anything is written.
  const errors = [];
  const fatal = (m) => errors.push(m);
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return { ok: false, errors: ["Not an object"], counts: null };
  }
  if (data.app !== "peptide-safety-tracker") {
    fatal("Not an export of this app (wrong app id).");
  }
  if (data.schema !== 1 && data.schema !== 2) {
    fatal("Unknown export schema version.");
  }
  if (!Array.isArray(data.profiles) || !data.profiles.length) {
    fatal("No profiles in export.");
  }
  const counts = { profiles: 0, usage: 0, symptoms: 0, observations: 0,
                   reminders: 0, productUnits: 0 };
  let total = 0;
  const profileIds = new Set();
  const seenIds = new Map();     // "store:id" -> owning profileId
  const checks = [
    ["usage", "usage", r => typeof r.peptideName === "string" &&
        r.peptideName.length > 0 && r.peptideName.length <= 200 &&
        Number.isFinite(Number(r.amount)) && Number(r.amount) > 0 &&
        Number(r.amount) < 1e12 && UNITS.includes(r.unit) &&
        validISODate(r.takenAt)],
    ["symptoms", "symptoms", r => typeof r.peptideName === "string" &&
        r.peptideName.length <= 200 &&
        typeof r.description === "string" && r.description.length <= 2000 &&
        Number.isInteger(r.severity) && r.severity >= 1 && r.severity <= 5 &&
        validISODate(r.loggedAt)],
    ["observations", "observations", r => validISODate(r.takenAt) &&
        (r.notes === undefined || (typeof r.notes === "string" &&
          r.notes.length <= 2000))],
    ["reminders", "reminders", r => typeof r.peptideName === "string" &&
        r.peptideName.length <= 200 &&
        /^[0-2][0-9]:[0-5][0-9]$/.test(r.timeOfDay)],
  ];
  if (Array.isArray(data.profiles)) {
    if (data.profiles.length > IMPORT_LIMITS.profiles) {
      fatal(`Too many profiles in export (limit ${IMPORT_LIMITS.profiles}).`);
    }
    for (const block of data.profiles) {
      if (!block || typeof block !== "object" || !block.profile ||
          !block.profile.id || !block.profile.name ||
          !IMPORT_ID_RE.test(String(block.profile.id)) ||
          String(block.profile.name).length > 80) {
        fatal("A profile block is missing its id or name (or the id/name is malformed).");
        continue;
      }
      if (profileIds.has(block.profile.id)) {
        fatal(`Duplicate profile id in export (${block.profile.id}).`);
        continue;
      }
      profileIds.add(block.profile.id);
      counts.profiles++;
      for (const [key, store, check] of checks) {
        if (!Array.isArray(block[key])) {
          fatal(`${key} list missing for ${String(block.profile.name)}.`);
          continue;
        }
        if (block[key].length > IMPORT_LIMITS[key]) {
          fatal(`Too many ${key} records for ${String(block.profile.name)} (limit ${IMPORT_LIMITS[key]}).`);
          continue;
        }
        for (const r of block[key]) {
          if (!r || typeof r !== "object" || !r.id ||
              !IMPORT_ID_RE.test(String(r.id))) {
            errors.push(`${key}: record without a valid id — record skipped on import.`);
            continue;
          }
          const seenKey = store + ":" + r.id;
          if (seenIds.has(seenKey)) {
            // the same record id under two profiles would make profileId
            // ambiguous — refuse the whole import instead
            fatal(`${key} (${r.id}): the same record id appears under more than one profile in this file.`);
          } else {
            seenIds.set(seenKey, block.profile.id);
          }
          total++;
          if (!check(r)) {
            errors.push(`${key} (${r.id}): invalid ${key === "usage" ? "amount/unit/date" : key === "symptoms" ? "severity/date" : "value"} — record skipped on import.`);
          } else {
            counts[key]++;
          }
        }
      }
      if (data.schema === 2) {
        // remembered product units (schema 2 only)
        if (block.productUnits !== undefined) {
          if (!Array.isArray(block.productUnits)) {
            fatal(`productUnits list invalid for ${String(block.profile.name)}.`);
          } else if (block.productUnits.length > IMPORT_LIMITS.productUnits) {
            fatal(`Too many productUnits for ${String(block.profile.name)} (limit ${IMPORT_LIMITS.productUnits}).`);
          } else {
            for (const u of block.productUnits) {
              if (!u || typeof u !== "object" || !u.id ||
                  !IMPORT_ID_RE.test(String(u.id)) ||
                  typeof u.name !== "string" || !u.name ||
                  u.name.length > 200 || !UNITS.includes(u.unit)) {
                errors.push("productUnits: invalid entry — skipped on import.");
                continue;
              }
              counts.productUnits++;
            }
          }
        }
      }
    }
  }
  if (total > IMPORT_TOTAL_LIMIT) {
    fatal(`Export too large (limit ${IMPORT_TOTAL_LIMIT} records).`);
  }
  const bad = errors.filter(e =>
    e.startsWith("Not") || e.startsWith("Unknown") ||
    e.startsWith("No profiles") || e.includes("missing") ||
    e.startsWith("Duplicate") || e.includes("more than one profile") ||
    e.startsWith("Too many") || e.startsWith("Export too large"));
  return { ok: bad.length === 0, errors, counts };
}

async function importFile(file) {
  let text;
  try { text = await file.text(); }
  catch { toast("Could not read the file", true); return; }
  if (text.length > 2 * 1024 * 1024) {
    showImportPreview({ ok: false,
      errors: ["File is larger than 2 MB — not a backup this app would produce."],
      counts: null });
    return;
  }
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
    <p class="text-xs text-slate-300">${v.counts.profiles} profile(s): ${v.counts.usage} doses, ${v.counts.symptoms} symptoms, ${v.counts.observations} observations, ${v.counts.reminders} reminders${data && data.schema === 2 ? `, ${v.counts.productUnits} remembered units` : ""}.</p>
    ${v.errors.length ? `<p class="text-xs text-amber-300">${v.errors.length} record(s) failed validation and will be skipped.</p>` : ""}
    <p class="text-xs text-amber-200/90">Sensitivity: this file contains private health notes. Importing adds them to this device's records — keep the file private and delete it when you're done.</p>
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
  let data = null;
  try { data = JSON.parse(box.dataset.payload || "null"); } catch { data = null; }
  if (!data) return;
  // Revalidate at apply time — the preview could be stale, and the payload
  // lives in the DOM where it could have been tampered with.
  const v = validateExport(data);
  if (!v.ok) { showImportPreview(v); return; }
  if (mode === "replace" && !confirm(
    "Replace EVERYTHING on this device with the export file? Current records will be permanently deleted.")) {
    return;
  }
  const clearStores = mode === "replace"
    ? ["profiles", "usage", "symptoms", "observations", "reminders",
       "goals", "meta", "productUnits"] : [];
  const writes = [];
  if (mode === "merge") {
    // dedupe against what is already on the device (records with an id
    // that exists here are skipped, not overwritten)
    const existing = new Set();
    for (const store of ["profiles", "usage", "symptoms", "observations",
                         "reminders", "productUnits"]) {
      for (const r of await Store.getAll(store)) existing.add(store + ":" + r.id);
    }
    const skip = (store, id) => existing.has(store + ":" + id);
    for (const block of data.profiles) {
      const pid = block.profile.id;
      writes.push({ store: "profiles", records:
        skip("profiles", pid) ? [] : [{ ...block.profile }] });
      writes.push({ store: "productUnits", records:
        (data.schema === 2 ? (block.productUnits || []) : [])
        .filter(u => u && u.id && IMPORT_ID_RE.test(String(u.id)) &&
               UNITS.includes(u.unit) && !skip("productUnits", u.id))
        .map(u => ({ ...u, profileId: pid })) });
      for (const [key, store, check] of [
        ["usage", "usage", r => Number(r.amount) > 0 && UNITS.includes(r.unit)],
        ["symptoms", "symptoms", r => r.severity >= 1 && r.severity <= 5],
        ["observations", "observations", () => true],
        ["reminders", "reminders",
         r => /^[0-2][0-9]:[0-5][0-9]$/.test(r.timeOfDay)],
      ]) {
        writes.push({ store, records: (block[key] || [])
          .filter(r => r && r.id && IMPORT_ID_RE.test(String(r.id)) &&
                 check(r) && !skip(store, r.id))
          .map(r => ({ ...r, profileId: pid })) });
      }
      writes.push({ store: "goals", records: [{
        id: pid, profileId: pid,
        goalKeys: (Array.isArray(block.goals)
          ? block.goals.filter(k => GOALS[k]) : []) }] });
    }
  } else {
    // replace: write the export's own meta keys after wipe
    for (const block of data.profiles) {
      const pid = block.profile.id;
      writes.push({ store: "profiles", records: [{ ...block.profile }] });
      writes.push({ store: "productUnits", records:
        (data.schema === 2 ? (block.productUnits || []) : [])
        .filter(u => u && u.id && IMPORT_ID_RE.test(String(u.id)) &&
               UNITS.includes(u.unit))
        .map(u => ({ ...u, profileId: pid })) });
      for (const [key, store, check] of [
        ["usage", "usage", r => Number(r.amount) > 0 && UNITS.includes(r.unit)],
        ["symptoms", "symptoms", r => r.severity >= 1 && r.severity <= 5],
        ["observations", "observations", () => true],
        ["reminders", "reminders",
         r => /^[0-2][0-9]:[0-5][0-9]$/.test(r.timeOfDay)],
      ]) {
        writes.push({ store, records: (block[key] || [])
          .filter(r => r && r.id && IMPORT_ID_RE.test(String(r.id)) && check(r))
          .map(r => ({ ...r, profileId: pid })) });
      }
      writes.push({ store: "goals", records: [{
        id: pid, profileId: pid,
        goalKeys: (Array.isArray(block.goals)
          ? block.goals.filter(k => GOALS[k]) : []) }] });
    }
  }
  try {
    await Store.importAtomic(writes, clearStores);
  } catch (e) {
    showImportPreview({ ok: false, errors:
      [e && e.message ? e.message : "Import failed — nothing was changed."],
      counts: null });
    return;
  }
  // Schema-1 imports have no productUnits in the file: rebuild remembered
  // units from each product's most recent usage record that was imported.
  if (data.schema === 1) {
    for (const block of data.profiles) {
      const perProduct = {};
      for (const u of (block.usage || [])) {
        if (typeof u.peptideName !== "string" || !UNITS.includes(u.unit)) continue;
        const k = u.peptideName.toLowerCase();
        if (!perProduct[k] || new Date(u.takenAt) > new Date(perProduct[k].takenAt)) {
          perProduct[k] = u;
        }
      }
      for (const [k, u] of Object.entries(perProduct)) {
        if (IMPORT_ID_RE.test(block.profile.id)) {
          await Store.rememberUnit(block.profile.id, u.peptideName, u.unit);
        }
      }
    }
  }
  box.classList.add("hidden");
  box.dataset.payload = "";
  $("#import-file").value = "";
  const added = writes.reduce((n, w) => n + w.records.length, 0);
  toast(`✓ Import complete — ${added} record(s) added (validated before anything was written)`);
  const first = (await Store.profiles())[0];
  await switchProfile(first ? first.id : null);
  if (!profile) $("#first-run").classList.remove("hidden");
  await loadAll();
}

// Delegated actions for record buttons (Log again / Correct / reminders).
// Record ids are NEVER interpolated into inline onclick attributes — they
// can come from an imported file, so they are read via dataset only.
const DELEGATED_ACTIONS = {
  "log-again": (id) => logAgain(id),
  "correct-dose": (id) => openLogSheet(id),
  "correct-obs": (id) => openObservationSheet(id),
  "toggle-reminder": (id) => {
    const r = lastReminders.find(x => x.id === id);
    if (r) toggleReminder(id, r.enabled === false);
  },
  "delete-reminder": (id) => deleteReminder(id),
};
document.addEventListener("click", (ev) => {
  const btn = ev.target.closest("[data-act]");
  if (!btn || !DELEGATED_ACTIONS[btn.dataset.act]) return;
  DELEGATED_ACTIONS[btn.dataset.act](btn.dataset.id);
});

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
  attachPicker("#u-name", "#u-name-dd", () => onProductChanged());
  $("#u-name").addEventListener("input", onProductChanged);
  attachPicker("#r-name", "#r-name-dd");
  $("#hist-q").addEventListener("input", renderHistory);
  $("#hist-type").addEventListener("change", renderHistory);
  $("#hist-from").addEventListener("change", renderHistory);
  $("#hist-to").addEventListener("change", renderHistory);
  $("#cat-q").addEventListener("input", renderCatalog);
  $("#import-file").addEventListener("change", ev => {
    if (ev.target.files[0]) importFile(ev.target.files[0]);
  });
  $("#profile-select").addEventListener("change", ev => switchProfile(ev.target.value));
});
