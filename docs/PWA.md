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

## Regenerating static data

After editing the catalog or goals in the Python seed:

```bash
.venv/bin/python -m tools.make_static_data   # rebuilds pwa/data.js
.venv/bin/python -m tools.make_icons         # rebuilds pwa/icons/*.png
```

Then bump `CACHE` version in `pwa/sw.js` (e.g. `-v2`) so installed clients
refresh their shell.
