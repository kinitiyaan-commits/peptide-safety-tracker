# Peptide App Resources

Source of this mapping: the user-provided CSV
(`Resource-Whatitcontributes.csv`, copied alongside this file). The app
**links out** to these sources and states their regulatory facts
verbatim-minimal; it does not republish or interpret medical content.

| Resource | What it contributes | Where it appears in the app |
| --- | --- | --- |
| FDA Drugs@FDA (https://fullexternal.fda.gov/op/data/cder/ndc) — use https://open.fda.gov/apis/drug/ | Product and approval records for checking regulatory information. | Brand/reference check panel: builds openFDA drug search deep links per product name. |
| DailyMed (https://dailymed.nlm.nih.gov) | Drug-label data and an API for accessing labeling and history. | Reference panel: DailyMed label search links; used as the canonical label source. |
| FDA peptide compounding concerns (https://www.fda.gov/drugs/human-drug-compounding) | Substance-specific safety concerns and compounding-policy context. | Catalog entries for non-approved peptides state only "not FDA-approved; see FDA compounding page" with the link. |
| FDA online-pharmacy guidance (https://www.fda.gov/consumers/buying-medicine-online) | Criteria for checking pharmacies, including licensure and prescription requirements. | Brand directory: "how to verify a seller" checklist link; no brand is pre-approved by the app. |
| NCBI E-utilities (https://eutils.ncbi.nlm.nih.gov) | Programmatic access to biomedical literature for the evidence library. | Milestone B: evidence tab fetches citation metadata (title/journal) for user-selected substances. |
| HHS health-app guidance (https://www.hhs.gov/hipaa/for-professionals/privacy/special-topics/health-apps/index.html) | Resources for assessing privacy obligations before handling real health data. | Privacy checklist page + `AGENTS.md` gate: real PHI collection is blocked until this review is done. |

## Notes

- Deep links are **constructed** from user-typed product names; the app never
  transmits user identifiers, symptoms, or usage history to these services.
- Regulatory statuses stored in the catalog are limited to the factual
  categories: `fda-approved`, `not-fda-approved`, `compounding-flagged`,
  `unknown`. Anything richer must cite the source URL inline.
