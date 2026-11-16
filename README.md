# Peptide Safety Tracker

A local-first, single-device journal for logging peptide use, symptoms, and
personal observations — with neutral, sourced regulatory reference
information. **This app is not medical advice.** It records what you enter,
never recommends doses, and never rates brands as safe or unsafe.

Two deliverables live in this repository:

| Deliverable | Location | Storage |
|---|---|---|
| Server prototype (FastAPI + SQLite) | `peptide_safety/` | local SQLite file (`peptide_safety.db`) |
| Installable static PWA | `pwa/` | browser IndexedDB only — nothing is sent to any server |

## Purpose

- Log doses the **user** enters (amount + explicit unit: `mcg`, `mg`, `IU`,
  `units`, `mL`), symptoms, and goal observations (sleep, weight, etc.) —
  goal fields are personal journal fields, never treatment claims.
- Show **regulatory status only** for catalog ingredients, each with a cited
  source (FDA / DailyMed / MedlinePlus). Ingredient-level statements such as
  "Approved products exist" never imply that any specific product you have
  is approved; check approval per exact product in
  [Drugs@FDA](https://www.accessdata.fda.gov/scripts/cder/daf/) and use
  DailyMed for labeling only, since DailyMed also lists products that are not
  FDA-approved.
- Link out to official sources (DailyMed, openFDA, FDA compounding pages)
  for verification. The app never interprets results or scores brands.
- Export the current profile's data as JSON/CSV. Nothing leaves the device
  except an export you explicitly create and share.

## Safety boundaries (by design, not by accident)

- No invented medical claims: every catalog efficacy/mechanism statement
  traces to a recorded source URL.
- No dose recommendations, no "safe/unsafe" brand ratings, no endorsements.
- Reminders are in-app-only and user-configured; the app never generates
  schedules or amounts.
- Corrections preserve the original values and timestamps in a correction
  history; nothing is overwritten destructively.
- Ships with **synthetic demo data only**. Do a privacy/security review
  ([HHS guidance](https://www.hhs.gov/hipaa/for-professionals/privacy/special-topics/health-apps/index.html))
  before storing real health records, especially on shared devices.

## Server prototype — setup and run

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # fastapi, uvicorn
.venv/bin/python -m peptide_safety.server      # http://127.0.0.1:8001
```

First run creates `peptide_safety.db` and seeds a synthetic demo profile.
The database is local-only and gitignored — never commit it.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

Covers: per-profile data isolation (user A never sees user B's records),
explicit-unit validation, correction history preservation, request
idempotency, the usage-goal-data → observations migration, export scoping,
blank-form-on-open static checks, and static checks for the PWA files.

The PWA itself is verified statically plus by hand in a desktop browser
(see `docs/PWA.md`); it has no Python code to unit-test.

## Architecture (server prototype)

```
peptide_safety/
  db.py        SQLite schema — every user-owned table carries user_id
  service.py   user-scoped CRUD, corrections, idempotency, migrations
  seed.py      synthetic demo data + sourced catalog (21 entries)
  goals.py     tracking-goal registry (journal fields, NOT indications)
  exporters.py JSON/CSV export, scoped to one profile
  server.py    FastAPI app + embedded HTML/JS UI
docs/          transcribed specs, reconciliation checklist, PWA notes
tests/         pytest suite (127 tests)
pwa/           static installable PWA (IndexedDB storage)
```

## Static PWA

`pwa/` is a fully client-side version: open `pwa/index.html` (or deploy the
folder to GitHub Pages / Netlify) and all records live in the browser's
IndexedDB on that device. Clearing browser data deletes them. See
`docs/PWA.md` for deployment steps and verification notes.

## Limitations

- **Single device, no authentication.** Profiles separate records but are
  not accounts; anyone who can use the device can open any profile.
- **No cloud backup.** Export a copy from Settings; deleted records cannot
  be recovered by the app.
- Reminders only fire while the page is open in a browser tab (no
  background scheduler in the server prototype).
- The PWA styles itself from a local, versioned stylesheet
  (`pwa/styles.css`) — no CDN or third-party runtime code is loaded.
  Catalog statuses are developer-verified against cited sources on the
  review date, not clinically reviewed; two entries remain marked
  `awaiting-verification` pending source review.
- The PWA's reminder and export features are equivalent, but its storage is
  per-browser (clearing site data deletes records — stated in-app).

## Disclaimer

This app is not medical advice. Many research peptides are not
FDA-approved; compounded copies carry FDA-documented risks. The app records
what you enter, never recommends doses, and never rates brands as safe or
unsafe. Verify anything important with official sources and a licensed
clinician.
