# OpenCode Catalog And Goals — STATUS

**The referenced document `docs/OPENCODE_CATALOG_AND_GOALS.md` was not found**
in the repository or the user's shared Downloads folder when this work began
(2026-11-14). This stub records what happened instead of silently skipping it.

## Implemented from the brief in the session prompt

- Catalog expansion with sourced candidates, name-based dedupe, existing logs
  preserved. Because the doc's exact candidate list is unavailable, candidates
  were sourced directly from DailyMed / FDA pages (regulatory status only).
  Entries whose status could not be fully confirmed are marked
  `awaiting-verification` in the new `review_status` metadata.
- HGH/height educational note (catalog entry + Learn-tab card).
- Source/review metadata columns: `review_status`, `source_type`,
  `last_reviewed`.
- Optional multi-select tracking goals that customize journal fields
  (personal metrics only — never medication recommendations), kept strictly
  separate from clinical indications.
- Privacy protections: goals and goal-journal data are per-profile, isolated,
  local-only, excluded from outbound links, and covered by tests.

## Not implemented / pending

- The document's own candidate list and acceptance tests are unknown; the
  entries marked `awaiting-verification` need the doc (or human review
  against FDA sources) to confirm.
- Do not invent additional doc requirements; ask the user to share the file.
