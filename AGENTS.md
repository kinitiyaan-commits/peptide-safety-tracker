# AGENTS.md — Persistent Project Constraints

These constraints apply to every change in this repository. They are additive
and must not be overwritten by later instructions unless a human explicitly
approves a change. Nonconflicting guidance elsewhere still applies.

## Scope of this repo

- `app.py` is the pre-existing "Apex Fitness" tracker. Preserve it; do not
  regress or delete it.
- `peptide_safety/` is the peptide safety/tracker application (Milestone A and
  onward). New peptide features belong there, not in `app.py`.

## Safety and content constraints (hard rules)

1. **No invented medical claims.** Any efficacy, mechanism, or evidence
   statement must trace to a real, citable source (FDA, DailyMed, NCBI
   literature) recorded in the data file or API response. When in doubt,
   state the regulatory status only.
2. **No dose recommendations.** The app records doses the *user* enters; it
   never suggests, normalizes, or ranks doses. Placeholder text may describe
   units, never amounts to take.
3. **Never mark brands as safe or unsafe.** Brand information is neutral:
   supplier type, region, and *links for the user to verify* against FDA /
   DailyMed / state licensure. No endorsements, ratings, or "trusted" labels.
3a. **Approval wording is ingredient-level, never product-implication.**
   The catalog must say "Approved products exist" (ingredient-level), never
   plain "FDA-approved" next to an ingredient name. Approval applies only to
   specific products, verified per exact product on DailyMed. FDA
   distinguishes approved products from unapproved versions of the same
   molecule (e.g., unapproved GLP-1 drugs — see docs/PEPTIDE_RESOURCES.md).
3b. **Catalog review metadata.** Every catalog entry carries `review_status`
   (`verified` or `awaiting-verification`), `source_type`, and a source URL.
   `awaiting-verification` entries must be visually distinct in the UI and
   must never imply a safety conclusion. Verify them against FDA/DailyMed
   before promoting to `verified`.
3c. **Tracking goals are personal journal fields, not indications.** Goal
   labels describe what the user wants to record (e.g., "Sleep quality"),
   never what a substance treats, cures, or causes. Clinical indication
   facts belong only in sourced catalog entries. Keep the two concepts in
   separate data structures, endpoints, and UI sections.
4. **Prominent disclaimers everywhere.** The app is not medical advice. Many
   research peptides are not FDA-approved; compounded copies carry
   FDA-documented risks. Every UI surface that shows a peptide or brand shows
   its regulatory status and a disclaimer.
5. **Explicit units always.** Every recorded amount carries an explicit unit
   from a fixed allowlist (`mcg`, `mg`, `IU`, `units`, `mL`). Unitless amounts
   are rejected at the API layer.

## Privacy constraints

6. **Local-first health data.** All user health data stays in the local SQLite
   database (`peptide_safety.db`). No third-party transmission of user data.
   The only outbound "lookups" are user-initiated deep links to public
   FDA/DailyMed sites; no personal data is included in those links.
7. **User-data isolation is tested.** Every read/write is scoped by `user_id`.
   A regression test must prove user A's data never appears in user B's
   queries or exports.
8. **Export is explicit.** Data leaves the machine only when the user clicks
   export. Exports are scoped to the requesting user only.
9. **Privacy assessment before real health data.** Before handling any real
   PHI, complete an HHS health-app privacy/security review (see
   `docs/PEPTIDE_RESOURCES.md`). Until then the app ships with synthetic demo
   data only.

## Feature constraints

10. **Reminders are user-configured only.** The app stores and displays what
    the user set; it never generates schedules, frequencies, or amounts.
11. **Regulatory checks are link-outs.** Brand/source verification is done by
    constructing DailyMed / openFDA / FDA-compounding search URLs — the app
    never interprets the result on the user's behalf.

## Milestones

- **A (current):** private peptide-use tracker — synthetic demo data, explicit
  units, user-configured reminders, symptom logging, export, tested
  user-data isolation.
- **B (planned):** regulatory reference library (Drugs@FDA, DailyMed label
  views), pharmacy/online-seller checklist per FDA guidance, literature
  evidence library via NCBI E-utilities, privacy checklist per HHS guidance.
