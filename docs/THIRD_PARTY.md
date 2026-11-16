# Third-party, license, and branding inventory

Date: 2026-11-15. Scope: everything shipped in this repository and served
by the static PWA (`pwa/`) or the server prototype (`peptide_safety/`).

## Runtime dependencies shipped to users

| Dependency | Where | Form | License | Notes |
|---|---|---|---|---|
| Local stylesheet (`pwa/styles.css`) | PWA | first-party file, versioned header | same as repo (see below) | Replaced the previous remote Tailwind CDN runtime script — no third-party code executes in the browser. |
| Browser platform APIs | PWA | none bundled | n/a | IndexedDB, Service Worker, Web App Manifest. |
| No other runtime dependencies | PWA + server | — | — | No analytics, no trackers, no fonts, no CDN calls. |

Tailwind was previously loaded at runtime from
`https://cdn.tailwindcss.com`. As of this pass the app ships a
hand-built, versioned subset (`pwa/styles.css`) covering exactly the
classes the app uses; the CDN is neither loaded nor precached. This
removes a third-party runtime dependency (and its logging/availability
implications) from every user page load.

## Server prototype

- Python 3 standard library only (http.server, sqlite3) — no third-party
  packages are required to run `peptide_safety/server.py`.

## Branding inventory

| Asset | Status |
|---|---|
| App name "Peptide Safety Tracker" | in-repo working title — `[OWNER TO CONFIRM]` final public name |
| Icons (`pwa/icons/*.png`) | generated in-repo by `tools/make_icons.py`; no third-party artwork |
| Logo | none — `[OWNER TO CONFIRM]` whether one is wanted before the public post |
| Domain/hosting | GitHub Pages under the owner's account — `[OWNER TO CONFIRM]` |

No third-party trademarks are used in the app UI. Product names in the
catalog are medication/ingredient names cited for regulatory reference
only; the app does not rate or endorse any brand, and no brand logos or
packaging imagery are included.

## License of this repository

No LICENSE file exists yet — `[OWNER TO CONFIRM]` the license before the
public Reddit post (public source without a license grants no one any
reuse rights, which may or may not be intended). Candidate options to
decide between: MIT, Apache-2.0, or no-license-private.

## Content provenance (safety-relevant)

- Catalog regulatory statements trace to cited official pages (FDA,
  DailyMed, MedlinePlus) recorded per entry in `pwa/data.js` and the
  server database; see `docs/PEPTIDE_RESOURCES.md`.
- Approval wording is ingredient-level ("approved products exist");
  per-product approval is checked by the user in Drugs@FDA via link-out.
- No medical efficacy claims are made anywhere in the UI; the app is not
  medical advice (stated on every surface that shows a substance).
