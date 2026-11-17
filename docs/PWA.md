# Static PWA — installable, browser-only storage

`pwa/` is a fully client-side version of the tracker. There is **no server
and no API**: every record lives in the browser's IndexedDB on the device.
The Python code under `peptide_safety/` remains the tested prototype; the
static app reuses its sourced catalog and goal registry via a generated
data file.

## Files

| File | Purpose |
|---|---|
| `index.html` | App shell (tabs: Today / History / Catalog / Settings, FAB chooser, sheets) |
| `app.js` | UI logic: logging, corrections history, duplicate guard, goals, reminders, export/import |
| `store.js` | IndexedDB layer — profiles, usage, symptoms, observations, reminders, goals, meta |
| `data.js` | GENERATED from the Python seed (`tools/make_static_data.py`) — sourced catalog + goals, no user data |
| `sw.js` | Service worker: precaches the app shell, cache-first, offline navigation fallback |
| `manifest.webmanifest` | Install manifest (`start_url: "./"` so it works under any subpath) |
| `icons/icon-192.png`, `icon-512.png` | GENERATED (`tools/make_icons.py`) — emerald/white-plus, maskable-safe |

## Run it locally

Any static file server works:

```bash
.venv/bin/python -m http.server 8080 --directory pwa
# open http://127.0.0.1:8080/
```

Opening `pwa/index.html` directly from disk also works for basic use, but
the service worker and install prompt need http(s), so use a local server
or a deployment for the full experience.

## Deploy to GitHub Pages

1. Push the repository to GitHub (the `pwa/` folder must be included;
   `peptide_safety.db` and exports are gitignored and must NOT be pushed).
2. Repo → **Settings → Pages → Source: Deploy from a branch** → pick the
   branch and `/ (root)`.
3. The app is served at `https://<user>.github.io/<repo>/` — all paths in
   `pwa/` are relative and the manifest uses `start_url: "./"`, so it works
   in the repo subpath without changes.

## Deploy to Netlify

1. **Add new site → Import an existing project** (or drag-and-drop the
   `pwa/` folder at app.netlify.com/drop).
2. Publish directory: `pwa`. No build command needed.
3. Netlify serves it over HTTPS with the service worker and manifest
   intact; install works from the browser menu.

## Install on a phone

Open the deployed URL in the phone browser:
- **Android/Chrome:** menu → *Add to Home screen / Install app*.
- **iOS/Safari:** Share → *Add to Home Screen*.

Installed, it opens standalone and works fully offline.

## Where the data lives (and dies)

All records are in the browser's IndexedDB for the origin you loaded the
app from. Settings states this explicitly:

- Nothing is sent to any server; there is no fetch() of user data anywhere
  in the app (checked in `tests/test_pwa.py`).
- **Clearing the browser's site data for this origin deletes every record
  permanently.** Use Settings → Export for a JSON backup first.
- Exports contain every profile on the device; import validates the file
  (shape, units, severities), shows a preview with counts, and offers
  Merge (keep existing + add) or Replace (wipe device first).
- Installations of the same app on two devices are separate databases;
  moving data between them is done via export/import.

## Verification notes (2026-11-15, desktop browser only)

Verified by hand in a desktop browser against a local server: profile
creation, dose/symptom/observation logging, blank forms on open, goal
chips (six common + More), observation fields from selected goals,
correction history preserved on edits, history filters, duplicate guard,
junk import refused with reasons, valid import preview (counts + invalid
records skipped), merge import restores profile and goals, service worker
registered, all shell assets (including the styling script) present in the
Cache Storage, data deleted after profile deletion.

**Not yet verified on a real phone** — no phone was available in this
environment: install prompt behavior, standalone display, safe-area
layout, iOS quirks, and real offline launch still need a manual check on
an Android/iOS device.

## Beta backlog "Now" slice (2026-11-15, branch `feature/beta-now`)

Implemented against this PWA (the deployed app) and browser-verified:

- **Explicit units:** new products start at "Choose unit"; saving without
  a unit is blocked; the last confirmed unit per product **per profile**
  is remembered (new `productUnits` store, DB v2) and shown with a  confirmation hint; changing products never carries over a unit.
- **Repeat logging:** "Log again" on any dose (Today + History) opens a
  reviewable pre-filled form — time set to now, notes never copied,
  review warning shown before saving.
- **Repeated taps:** submit buttons are guarded — one deliberate save
  creates one record (browser-verified with concurrent double submits).
- **Data preservation:** DB v1→v2 upgrade verified against a populated
  installation (8 stores, zero loss); upgrades only create missing
  stores, never delete; "Update available" banner is manual-reload only
  so an unfinished form can never be interrupted; CACHE version bumped
  so installed clients refresh.
- **Backup:** export records the last successful backup time; a
  dismissible reminder appears when there is no backup or the last one is
  ≥7 days old (dismissal lasts a week).
- **Understandability:** version identifier in Settings; install help per
  platform with offline limitations; feedback section warning testers not
  to include medical records or identifying details (the app never
  attaches data to anything automatically).
- **Timeline:** date-range filters (from/to) added to History alongside
  text and type filters.
- **Appointment summary (standout):** date-range picker, live preview of
  exactly what will be shared, private notes excluded by default with an
  explicit opt-in, user-written questions included, print/download
  self-serve (nothing is sent anywhere), labeled as user-entered and
  possibly incomplete with no cause/effect claims.

Regression tests for all of the above live in `tests/test_pwa.py`
(classes `TestExplicitUnits`, `TestRepeatLogging`, `TestDataPreservation`,
`TestInstallAccessibilityFeedback`, `TestCombinedTimeline`,
`TestAppointmentSummary`).

## Pre-Reddit release blockers (2026-11-15, branch `feature/beta-now`)

Implemented after the branch was reconciled with main (merge `6b69a6c`),
keeping main's downward picker fix and unique profile form IDs:

- **Local styling, no CDN:** `pwa/styles.css` (versioned, comment header
  matches the SW cache version) replaces the Tailwind CDN `<script>`;
  removed from `index.html` and from the SW precache. Every class used by
  the app is covered (verified by a build-time class-inventory check and
  visually in the browser).
- **Controlled service-worker updates:** `sw.js` rewritten — strict
  install (`cache.addAll`, an asset failure keeps the old worker), no
  automatic `skipWaiting` (the worker waits until the user taps
  "Reload & update", which posts `ACCEPT_UPDATE`), activation deletes only
  `peptide-safety-static-*` caches, CACHE_PREFIX-based versioning.
- **App-side update flow:** the banner shows for a newly installed worker
  AND for an already-waiting one; applying the update first captures an
  unsaved log/symptom/observation/summary draft to `sessionStorage`
  (confirm dialog: OK = save draft and reload, Cancel = keep working);
  after the reload the draft is restored to its sheet. Reload happens
  once, on `controllerchange`. Verified end-to-end in the browser,
  including draft capture, restore, and activation.
- **DB-upgrade safety:** `onversionchange` closes the connection so a newer
  tab can upgrade; `onblocked` surfaces "close other tabs" via a toast
  instead of hanging silently. **Rollback:** production opens database
  version 1 and this branch opens version 3 (v2 added `productUnits`, v3
  added `vials`) — an old build that requests
  version 1 against an upgraded database fails with `VersionError`, so a
  rollback CANNOT be a plain code revert. Rollback must ship a
  DB-compatible build: `openDB()` in this branch already falls back to
  opening without an explicit version on `VersionError`, so future
  downgrades of this branch's own code are safe, but reverting to the
  currently deployed v1 build would not be — that path must be patched
  and tested before being relied on. The upgrade itself only creates
  missing stores and never deletes. Browser-verified: a real v2 database
  with a legacy record upgraded to v3 in place — record survived, the new
  `vials` store was created and works.
- **Atomic imports:** `Store.importAtomic` writes every record of an
  import in ONE multi-store transaction (replace-mode clears stores inside
  the same transaction, not before it). `validateExport` hardened: schema
  1 or 2, ID pattern `^[A-Za-z0-9_-]{1,64}$`, 2 MB file cap, per-store and
  total record limits, finite amounts, valid ISO dates, allowed units and
  severities, duplicate profile ids and the same record id under two
  profiles are fatal. Imports are revalidated at apply time. Verified in
  the browser: an aborted transaction leaves existing data untouched.
- **No XSS via imported data:** record ids are never interpolated into
  inline `onclick` attributes (buttons use `data-act`/`data-id` with one
  delegated listener); `esc()` now escapes quotes so it is safe inside
  attributes. Verified: a hostile import renders inert (no `<img>`/`<script>`
  execution, malicious ids are rejected by validation).
- **Remembered-unit race guard:** the async lookup in
  `onProductChanged` checks a monotonic token, the open-sheet epoch, and
  the current product text before applying a result — a slow lookup for
  an earlier product can never overwrite a newer state (verified with a
  deliberately slow stub lookup).
- **Backup wording honest:** "Last export initiated" (the app cannot see
  whether the file survived) plus a verify-the-file reminder; export
  schema 2 includes remembered `productUnits`; schema-1 imports rebuild
  remembered units from each product's most recent usage record.
- **Summary dates:** reversed From/To ranges are rejected in the preview,
  print, and download paths; periods are matched by local calendar day
  (consistent with the History filters); a sensitivity note is included
  even when private notes are excluded.
- **Accurate privacy wording:** no "never transmits anything" claims;
  the in-app text now says GitHub Pages (hosting) receives IPs and standard
  logs when the shell loads, and that verification links include the
  product name being checked. The feedback destination is explicitly
  marked pending the owner's decision, with a public-tracker warning.
- **No age collection:** the PWA's optional age input was removed (adult
  audience; the number served no purpose). Profile forms already read
  values from the submitted form.
- **privacy.html / terms.html:** drafted with clearly-marked
  `[OWNER TO CONFIRM]` placeholders (operator/contact/liability are owner
  decisions), linked from the first-run screen and Settings → Where your
  data lives, and included in the SW precache so they open offline.
- **Drugs@FDA link-out** added to the catalog's verification links
  (approval checked per exact product; DailyMed for labeling only).

Browser-verified (desktop, Chromium) at the commit noted in the release
report: controlled update with waiting worker and open form; aborted
import leaves data intact; hostile import inert; stale unit lookup
discarded; reversed summary range rejected; schema-2 export round-trip;
schema-1 rebuild of remembered units; offline relaunch serves the shell
and privacy/terms from cache; profile isolation (profile B sees none of
profile A's records).

**Still untested without a real phone:** install prompt, standalone
display, safe-area layout, and true offline launch from the home-screen
icon. Owner must run these before the Reddit post.

## Correction pass (review of `859a664`, 2026-11-15)

Four review corrections, all implemented and browser-verified; SW cache
bumped to v5 because app code changed:

- **ACCEPT_UPDATE now targets `registration.waiting`** — the installed,
  not-yet-active worker — via a retained `_swReg` reference; messaging
  the active controller remains only as a stale-banner fallback.
  Browser-verified: the waiting v5 worker (not the active v4) was
  activated by the button.
- **`Store.onBlocked` is registered at the top of `init()`, before any
  storage access**, and boot failures are surfaced visibly ("The app
  could not start: …" banner + console) instead of a silent
  half-initialized app.
- **Drafts carry full context:** profile ID and the record ID being
  corrected; restore switches back to the owning profile and reopens the
  sheet in correction mode ("Correct entry", same `editingUsageId`).
  Storage-failure honesty: if sessionStorage write fails, the confirm
  says the entry WILL BE LOST instead of promising restoration; the
  stored draft is consumed only after its fields are successfully
  applied. Browser-verified end-to-end, including the failure path.
- **Rollback claim corrected:** production opens DB v1; an old build
  requesting v1 against an upgraded DB gets `VersionError` — a rollback
  is NOT a plain code revert. `openDB()` now falls back to opening
  without an explicit version on `VersionError` (additive-upgrade
  handling is safe at any version). Browser-verified: DB manually
  upgraded to v3 → app declares v2 → still works, records readable,
  writes fine, DB left at v3 (non-destructive). Rolling back to the
  currently deployed v1 build would still require a patched build and
  testing.

Two-tab update verified in the browser: tab A accepted the update with an
unfinished correction open; tab B, holding an unfinished symptom form,
preserved its draft silently on `controllerchange` (per-tab sessionStorage)
and restored it after its own reload. `controllerchange` ignores the
first-install claim (no pointless reload when the SW first controls the
page).

Policy drafts corrected, not just placeholders: privacy/terms now
disclose per-tab sessionStorage for unsaved entries and state plainly
that a backup file includes every profile on this device (the in-app
"Where your data lives" note matches).

Executable tests for all of the above were added to `tests/test_pwa.py`
(classes `TestUpdateTargetsWaitingWorker`, `TestOnBlockedRegistrationTiming`,
`TestDraftContextPreserved`, `TestRollbackClaimAccuracy`,
`TestPolicyDraftAccuracy`). Full suite: 182 passed.

## Release-candidate pass (2026-11-15, from `71d09cf`)

Feature-freeze pass: one small requested feature, then the release items.
SW cache at **v7** (three bumps during the pass as code changed).

**Training context (optional observation section).** A collapsed
`<details id="training-context">` in the observation sheet: session type,
muscles trained, perceived session effort (1–5), soreness (1–5), and a
private note. Wording is neutral throughout — "Your own training notes for
your records… The app draws no connection between training and any
product." No dose, product, or outcome claims anywhere. Implementation:

- Stored in the observation's existing `goalData` under `tc_` keys
  (`tc_session_type`, `tc_muscles`, `tc_effort`, `tc_soreness`,
  `tc_note`) — no new stores, no schema change, so correction history,
  backup/restore, and per-profile isolation come free via the
  `goalData` passthrough.
- `collectGoalData()` now reads `#observation-fields .gf, #training-fields
  .gf`; the details element is collapsed on every `openObservationSheet()`
  open (values still prefill in correction mode while collapsed).
- History renders `tc_*` with human labels (`TC_LABELS`), including the
  private note — history is the user's own view.
- Appointment summaries map the same labels but **exclude `tc_note`
  unless the user opts into notes** for that summary.
- Verified in the browser: save → history labels, correction prefill
  (collapsed), summary exclusion/opt-in, export→import round-trip
  preserving all `tc_*` values (schema 2).

**Draft-loss fix (`controllerchange`).** `saveDraftSilently()` now returns
the `storeDraft()` result. The `controllerchange` handler in a
non-initiating tab no longer reloads unconditionally: on storage-write
failure it shows an explicit choice — "OK" reloads and the unfinished
entry WILL BE LOST; "Cancel" keeps working and the update applies on the
next reload — keeping the form visible and discarding nothing without
consent. Verified with two tabs: tab B (non-initiating) had an unfinished
form **and forced sessionStorage-write failure**; tab A accepted the
update; tab B showed the warning, Cancel left the form open with its
content intact and no reload. Single-tab `captureDraftForUpdate()` confirm
behavior unchanged.

**Bug found and fixed during verification:** `restoreDraft()` only queried
`#observation-fields .gf`, so an observation draft's **training-context
fields were not restored** after an update reload (dose/goal fields were).
Now queries `#observation-sheet .gf`, covering both containers. Re-verified
end-to-end: all five `tc_*` values restored after a real update cycle.

**Owner details (structure approved in one message).** Operator published
under a **public handle, not a personal name**; feedback goes to **GitHub
Issues on this repository** (public — warning not to post health data,
present in privacy.html and the in-app Feedback section); a separate
**private security/privacy email** for security/privacy reports. The two
literal values (handle, email) remain marked `[OWNER TO SUPPLY]` in
privacy.html/terms.html and must be filled before deployment.

**Policy finalization.** terms.html no longer asserts "not a medical
device" as a legal conclusion — it describes intended functionality (what
the app does/does not do). Liability wording no longer implies the terms
eliminate liability ("nothing in these terms limits or excludes any
liability that cannot be limited or excluded under applicable law"), with
final wording flagged as an owner decision. An "Open legal questions"
section surfaces unresolved items (applicable jurisdiction/rules,
device-regulation question, liability wording, license). privacy.html
covers: IndexedDB records, per-tab sessionStorage drafts, GitHub Pages
hosting logs, external product-name searches, all-profile backups, and
that downloaded/shared files leave the app's control. Suite: 200 passed.

## Final feature pass from Reddit feedback (2026-11-16, from `af31a2b`)

Owner-approved final scope based on r/Peptides feedback. SW cache **v8**,
DB **v3** (adds the `vials` store). Three mistake-catching features and a
UI-consistency pass. No syringe calculator (explicitly deferred by the
feedback); reminders remain in-app only (native notifications = the
Capacitor discussion, out of scope).

**1. "Already logged today" warning (double-dose catch).** While the dose
form is open, a live amber hint shows the user's most recent same-product
entry from TODAY: "You already logged TestPeptide today at 9:02 AM." On
save, a non-blocking guard repeats it inline and requires a second "Save
entry" to keep both entries — a forgotten earlier dose can't be silently
doubled, but a legitimate second dose is never refused. Reads only the
user's own records for the active profile; corrections don't flag
themselves. Browser-verified live hint + two-step save.

**2. Both units shown (unit-mix-up catch).** While typing, the form shows
the same amount in both scales: "300 mcg = 0.3 mg — same amount, both
units." Pure ×1000 conversion between mcg and mg only; IU/units/mL get no
conversion (those scales aren't inter-convertible and the app doesn't
guess). No syringe math, no dose suggestion — it always displays exactly
the amount the user typed. Browser-verified both directions + IU hiding.

**3. Vial log (forgotten-mix-date catch).** Settings → "Vial log": the
user records product name, the date mixed, and a discard date **the user
chooses**. The list shows the dates and a plain day count ("11 days from
today"). Neutral wording: the app "does not calculate stability, recommend
dates, or advise any use." Stored in a new per-profile `vials` store
(DB v3, additive upgrade), included in export (schema 3; old schema 1/2
backups still import) with strict validation, wired into the profile
delete cascade. Browser-verified: add/edit/delete (delete confirmed),
discard-before-mix refused, export→import round-trip, and a real v2→v3
upgrade preserving a legacy record.

**UI consistency (dark-theme fixes).** The "random white spots" were
browser-default surfaces: bare buttons (bottom nav, close ×, text links)
rendered light-gray, and native date/time/file controls plus autofill
rendered white. Fixed with `color-scheme: dark`, a bare-button reset that
never overrides `.btn`/`.btn2`/`.fab`, dark `::file-selector-button`,
calendar-picker-indicator tinting, dark autofill, selection, and
scrollbars. Verified by screenshots: bottom nav, Settings, History
(date pickers), and the log sheet are uniformly dark. Suite: 217 passed.

**Dev note:** after changing app files, the browser's HTTP cache can keep
serving stale assets to `python -m http.server` dev origins (no
cache-control headers → heuristic caching), so an SW re-register may
precache stale bytes. Workaround used in testing: serve on a fresh port
(8081) or hard-refresh asset URLs. This is a dev-server artifact only —
GitHub Pages sends proper caching headers and the SW cache versioning
handles updates in production.

## Regenerating static data

After editing the catalog or goals in the Python seed:

```bash
.venv/bin/python -m tools.make_static_data   # rebuilds pwa/data.js
.venv/bin/python -m tools.make_icons         # rebuilds pwa/icons/*.png
```

Then bump `CACHE` version in `pwa/sw.js` (e.g. `-v2`) so installed clients
refresh their shell.
