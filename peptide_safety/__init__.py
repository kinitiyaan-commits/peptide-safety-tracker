"""Peptide Safety — private, local-first peptide use tracker (Milestone A).

Constraints (see AGENTS.md):
- No medical claims, no dose recommendations, no brand safety ratings.
- Explicit units on every recorded amount (mcg / mg / IU / units / mL).
- All health data stays in a local SQLite file; exports are user-initiated.
- Every read/write is scoped by user_id; isolation is regression-tested.
"""

__version__ = "0.1.0"

ALLOWED_UNITS = ("mcg", "mg", "IU", "units", "mL")

REGULATORY_STATUSES = {
    "fda-approved": "FDA-approved product (verify exact product on DailyMed)",
    "not-fda-approved": "Not FDA-approved for human use (see FDA compounding page)",
    "compounding-flagged": "Named in FDA compounding risk context (verify at fda.gov)",
    "unknown": "Regulatory status not established here — verify manually",
}

SEVERITY_MIN, SEVERITY_MAX = 1, 5
