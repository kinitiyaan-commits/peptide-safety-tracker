# Reconciliation checklist — implementation vs. the two original specifications

Date: 2026-11-14. Specs: `docs/OPENCODE_USABILITY_UPDATE.md` and
`docs/OPENCODE_CATALOG_AND_GOALS.md` (transcribed from the user's PDFs; the
former missing-document stubs are backed up in `docs/archive/`).

Legend: ✅ implemented and tested · 🟡 partially implemented · ❌ missing ·
🔒 blocked / awaiting source or device review

## Catalog (OPENCODE_CATALOG_AND_GOALS.md)

- ✅ Dedupe before adding; no duplicate names or aliases (tested).
- ✅ Exact spec candidates present with verified source URLs and domains:
  Somatropin/Tesamorelin/Liraglutide/Dulaglutide/Teriparatide/Abaloparatide
  (MedlinePlus), GHK-Cu/AOD-9604/Thymosin-alpha 1 (FDA bulk-substance page).
  Catalog is now **21 entries**.
- ✅ FDA bulk entries keep nomination/category context; withdrawn nominations
  are never presented as approval or clearance (tested).
- ✅ GHK-Cu keeps the injectable-route qualification (tested).
- ✅ Ibutamoren promoted from `awaiting-verification` to `verified` — FDA
  documents it directly (category 2, significant safety risks, congestive
  heart-failure signal) on the same FDA page.
- ✅ Section renamed "Peptides & related medications".
- ✅ Reviewed aliases in data + search: "HGH" resolves to Somatropin and
  explains the relationship instead of silently substituting (tested).
- ✅ Data-driven edits via `refresh_catalog()` migration, stable row IDs.
- ✅ New entries carry source/review metadata; unknowns stay unknown
  (`Sermorelin`, `Melanotan II` remain `awaiting-verification`).
- ✅ Historical/availability-sensitive: pramlintide and exenatide deliberately
  NOT imported as available (tested absent).
- 🟡 Generic vs exact product records separately; formulation/route/
  jurisdiction columns — the schema has category and notes carrying this, but
  there is no dedicated `formulation`/`route`/`jurisdiction` column set yet.
- ❌ Injectable vs topical formulation separation beyond the GHK-Cu note.
- ❌ Sort catalog by personal saved products / recent use / alphabetical.
- 🔒 Reviewed date lifecycle ("what reviewed means"): currently `last_reviewed`
  = date the row was sourced/verified against the cited page by the developer.
  A human review workflow (re-review schedule, reviewer identity) is not built.

## Goals (OPENCODE_CATALOG_AND_GOALS.md)

- ✅ All 10 spec-suggested labels exist as stable goal keys, editable in
  Settings, optional multi-select (tested); "custom" goal with private custom
  text stored per profile (tested, isolated, escaped in UI rendering).
- ✅ Required explanation text shown verbatim (spec quote).
- ✅ Journal fields: weight + optional waist, training/recovery (soreness +
  activity notes), skin/hair text, sleep duration + subjective energy,
  prescribed-treatment context + visit questions, appearance private notes,
  clinician-managed growth measurements + visit notes. All optional; selecting
  a goal never selects a peptide, prefills dose, ranks brands, or hides
  warnings (architecturally impossible: goals and catalog are separate tables,
  endpoints, and UI sections; tested).
- ✅ **Changing a goal never deletes/invalidates historical observations or
  medication records** (tested explicitly, incl. re-enabling).
- ✅ Goals included in export and deletion flows; isolated per user (tested).
- ✅ **Independent observation logging** — new `observations` table, sheet,
  endpoints, history/export: record sleep/height/weight/etc. with **no
  administration event** (tested).
- ✅ HGH/height guardrail: spec's suggested note text shown verbatim (Learn
  card, Settings when a height goal is selected, and Learn catalog when
  searching "HGH"), linked to Cleveland Clinic + MedlinePlus; risks named
  (swelling, joint/muscle pain, insulin resistance); never infers growth-plate
  status from any app data (no such code exists).
- ✅ Adult-only scope unchanged; no pediatric workflows added.
- ✅ Goal chips during **onboarding** (spec: chips at onboarding, editable
  later). New optional "What would you like to track?" step (step 3 of 4) with
  **Skip**; saves the same stable goal keys as the Settings editor, which is
  preserved unchanged. Browser-verified end-to-end.
- ❌ Charts of recorded observations with units/gaps.
- ❌ Photos for skin/hair (spec says defer — correctly deferred).

## Logging & history (OPENCODE_USABILITY_UPDATE.md)

- ✅ Searchable combobox with aliases, saved/recent first, "new" unlisted
  entries labeled user-entered/unverified, records never rejected for missing
  catalog entry (existing behavior, kept).
- ✅ Time defaults to now; backdated entries accepted; inline validation
  preserving values (existing, kept).
- ✅ **Server-side duplicate protection** (spec: not just a disabled button):
  same product/amount/unit within 120 s → HTTP 409 prompt with an explicit
  override path that still records the entry (tested at service + API + UI).
- ✅ Save confirmation shows product + timestamp with **Undo**; duplicate
  prompts without blocking intentional entries (tested).
- ✅ Weekday **chips + Every day** replace the free-text weekday field.
- ✅ **Reminder honesty**: labeled in-app-only everywhere (Today card,
  reminder card, add-toast); permission status + test notification implemented
  with honest denied/unsupported states; pause/resume/delete; "not logged"
  never called "missed"; no catch-up instructions.
- ✅ Timezone/DST definition: reminder times are wall-clock HH:MM rendered in
  device-local time, stored verbatim (tested); the app has **no background
  scheduler**, so nothing fires when closed and nothing keeps firing after
  pause/delete (tested).
- ✅ **History edits**: every usage entry and observation can be corrected from
  History; each edit appends `{edited_at, previous:{...}}` to the row's
  `corrections` list (original and intermediate values + timestamps preserved,
  never overwritten). History shows an "✎ edited" marker plus the full
  correction log; JSON/CSV exports include corrections. Tested (service, HTTP,
  migration, export) and browser-verified.
- ✅ **Request idempotency**, separate from the duplicate guard: client
  generates one key per form session; a retried POST with the same key replays
  the original response and never creates another event (tested: replay vs
  409-duplicate are distinct paths; keys are scoped per user; keys cascade-
  delete with the user). UI toast explicitly says "retry confirmed, not
  duplicated" on replay.
- 🟡 History edits for symptoms: view + delete only; symptom correction not
  yet implemented (low risk of accidental change, but incomplete).
- 🟡 Snooze and skip (spec lists pause, resume, snooze, skip, cancel) — pause
  ✅, resume ✅, cancel ✅, snooze/skip ❌ (would need per-day state).
- ✅ **History filters**: product text, from/to date range, event type
  (administrations / observations / symptoms) with Clear-filters, a live
  match count, card hiding by event type, honest empty states
  ("no entries match the current filters" vs "nothing logged yet"), and a
  stated rule that the product filter applies to administrations/symptoms only
  (observations carry no product). Browser-verified.
- ✅ **Visit summary**: printable window for a selected (default: last-30-days)
  date range honoring the product filter; separates actual administrations,
  observations (no dose attached), self-rated symptoms, and planned reminders
  (explicitly labeled "schedule only — not a record of anything taken");
  includes units, timestamps, `[edited]` markers with previous values, and a
  user-entered-data disclaimer stating the app verifies nothing and implies
  no cause/effect/effectiveness. Popup-blocked fallback is a toast.
- ✅ Catalog badge renamed **"Reviewed" → "Source checked"** with an inline
  legend: source verification by the developer against the cited official
  page, **not qualified clinical review**, never implying safety or
  endorsement. Per-entry line now reads "source-checked <date>".
- ❌ Timeline/calendar view.
- ❌ Trends/charts.
- ❌ Offline save/pending/retry states (page is served by a local process;
  "offline" means the server process stopped — shows browser error, loses
  nothing but gives no retry UI).
- 🟡 Product records: saved products have name/default unit/notes; label
  strength, lot, expiration, manufacturer fields not yet added.

## Privacy / architecture (both docs)

- ✅ Documented honestly: single-device local app; **profile separation is not
  authentication** — anyone using the device can open any profile; no
  passwords; nothing leaves the machine without an explicit user action
  (Settings privacy card rewritten, matches tested implementation).
- ✅ Exports scoped per profile with tested cross-user isolation; observations
  and goals included; deletion semantics documented.
- ✅ No third-party transmission, analytics, or external AI (no such code).
- 🔒 Review gate: synthetic data only until security/privacy/clinical/regulatory
  review — unchanged (AGENTS.md rule 9).
- 🔒 Usability test with five consenting adults — requires explicit user
  approval to contact testers; not started.

## Report discrepancies reconciled

- **Five vs six:** the previous session's report said "6 verified sourced
  entries" but listed only 5 names — the actual additions at that time were
  **5** (Somatropin, Tesamorelin, Setmelanotide, Bremelanotide, Liraglutide);
  Setmelanotide and Bremelanotide were my DailyMed-sourced extras beyond the
  spec's list. The current count is 21 entries total, with the spec's 9
  candidates all present and sourced as specified above.
- A source URL alone does not make a claim "clinically verified" — entries
  carry regulatory/regulatory-adjacent statements quoted from the cited page
  only; "reviewed" means developer-verified against that page on
  2026-11-14, not clinical endorsement.

## Suggested next slices (small)

1. Symptom entry correction (same corrections mechanism as usage/observations).
2. Trends view of observations/measurements.
3. Reminder snooze/skip (per-day state), richer product fields
   (strength/lot/expiration), catalog formulation/route/jurisdiction columns.
4. Calendar/timeline history view; offline pending/retry states.

## Phone/GitHub readiness slice (2026-11-15)

- ✅ New entries always open with blank Notes/fields — `form.reset()` on
  every sheet opener (log, observation, symptom), static-checked in tests.
- ✅ The **+** button opens a single chooser (Dose / Observation / Symptom);
  the duplicate logging buttons were removed from Today.
- ✅ Goal fields removed from the dose form (they belong only in
  Observations). Existing `usage_log.goal_data` migrates one-time into
  linked Observations rows via `migrate_usage_goal_data_to_observations()`
  (idempotent, app_meta marker, non-destructive to the original rows;
  values are copied unvalidated so nothing is lost if a goal was later
  disabled). Tested without loss, cross-user isolation, and idempotency.
- ✅ Long disclaimers compressed to one line each with expandable
  **"Learn more"** `<details>` (Today banner, onboarding step 1, reminder
  honesty, privacy card, "Source checked" legend) — meaning kept.
- ✅ Product picker dropdown opens **upward** (`bottom:100%`) so it never
  covers Amount/Unit; also closes on outside click.
- ✅ Six common goal chips (sleep, bodyweight, energy, recovery, symptoms,
  appearance) with the remaining 12 behind a **"More goals (n)"** toggle in
  Settings and onboarding; any already-selected goal always stays visible.
- See also the static PWA deliverable in `pwa/` and its notes in
  `docs/PWA.md`.

## Static PWA slice (2026-11-15)

- ✅ `pwa/` runs as static files with **no server and no API** — all
  records live in browser IndexedDB (`store.js`); no fetch() of user data
  anywhere (statically tested).
- ✅ Installable: web manifest (`start_url: "./"`, subpath-safe), generated
  maskable icons, service worker precaching the shell, offline navigation
  fallback, cross-origin styling script cached with a no-cors fallback.
- ✅ Full export (every profile) + import/restore with strict validation,
  preview counts, skipped-record reporting, and merge-or-replace modes.
- ✅ Settings states plainly: data lives only on this device; clearing
  browser site data deletes every record; export is the backup path.
- ✅ Safety surfaces carried over: one-line disclaimers with "Learn more",
  single FAB chooser, no goal fields on doses, explicit-unit allowlist,
  duplicate guard, correction history, in-app-only reminders, ingredient-
  level approval wording, `awaiting-verification` visually distinct,
  sourced catalog with FDA/DailyMed link-outs.
- ✅ Deploy documented for GitHub Pages and Netlify (`docs/PWA.md`).
- 🔒 Real-phone verification (install prompt, standalone, safe areas,
  offline launch) — no phone available in this environment; listed as a
  manual follow-up.
