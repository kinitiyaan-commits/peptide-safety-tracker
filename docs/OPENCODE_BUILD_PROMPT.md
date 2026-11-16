# OpenCode Build Prompt (Milestone A)

Captured build brief for this phase of the peptide safety app.

## Brief

Build an app that can track peptide usage, recommend different brands, and act
as an overall peptide safety app, grounded in these resources:

| Resource | What it contributes |
| --- | --- |
| FDA Drugs@FDA | Product and approval records for checking regulatory information. |
| DailyMed | Drug-label data and an API for accessing labeling and history. |
| FDA peptide compounding concerns | Substance-specific safety concerns and compounding-policy context. |
| FDA online-pharmacy guidance | Criteria for checking pharmacies, including licensure and prescription requirements. |
| NCBI E-utilities | Programmatic access to biomedical literature for the evidence library. |
| HHS health-app guidance | Resources for assessing privacy obligations before handling real health data. |

## Process requirements

1. Read `docs/PEPTIDE_RESOURCES.md` and `docs/OPENCODE_BUILD_PROMPT.md` before
   making changes.
2. Inspect the existing repository. Preserve existing code and conventions.
3. Add the persistent project constraints to `AGENTS.md` without overwriting
   nonconflicting instructions.
4. Implement **Milestone A** first: a private peptide-use tracker with
   synthetic demo data, explicit units, user-configured reminders, symptom
   logging, export, and tested user-data isolation.
5. Do not invent medical claims, recommend doses, or mark brands as safe.
6. Run the relevant tests and report what works, what is mocked, and what
   remains blocked.

## Status note

- `docs/PEPTIDE_RESOURCES.md` and this file did not exist when work began
  (2026-11-13); they were created from the brief above so future sessions can
  read them first, as required.
- "Recommend different brands" is implemented within the safety constraints:
  a neutral brand directory plus verification link-outs (DailyMed, openFDA,
  FDA compounding / online-pharmacy pages). No brand is rated or endorsed.
