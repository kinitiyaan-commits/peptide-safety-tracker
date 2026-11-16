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
  is remembered (new `productUnits` store, DB v2) and shown with a
  confirmation hint; changing products never carries over a unit.
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
  instead of hanging silently. Rollback note: the upgrade path only
  creates missing stores; reverting code does not need a DB downgrade
  (older code ignores the extra `productUnits` store).
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

## Regenerating static data

After editing the catalog or goals in the Python seed:

```bash
.venv/bin/python -m tools.make_static_data   # rebuilds pwa/data.js
.venv/bin/python -m tools.make_icons         # rebuilds pwa/icons/*.png
```

Then bump `CACHE` version in `pwa/sw.js` (e.g. `-v2`) so installed clients
refresh their shell.
