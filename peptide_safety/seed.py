"""Synthetic demo seed data. All entries are demonstration-only.

Regulatory statements are limited to factual categories with a source URL
(AGENTS.md rule 1). Nothing here describes how anyone should use a substance.
"""

import json

from .db import init_db

CATALOG_ROWS = [
    # (name, category, regulatory_status, evidence_note, source_url,
    #  review_status, source_type)
    (
        "Semaglutide",
        "GLP-1 receptor agonist (ingredient)",
        "fda-approved",
        "Approved products exist for this ingredient (e.g., Ozempic, Wegovy) — "
        "approval applies to those specific products only. FDA has also raised "
        "concerns about unapproved GLP-1 versions; verify any exact product on "
        "DailyMed before treating it as approved.",
        "https://www.fda.gov/drugs/drug-alerts-and-statements/fdas-concerns-unapproved-glp-1-drugs-used-weight-loss",
        "verified", "fda",
    ),
    (
        "Tirzepatide",
        "GIP/GLP-1 receptor agonist (ingredient)",
        "fda-approved",
        "Approved products exist for this ingredient (e.g., Zepbound, Mounjaro) "
        "— approval applies to those specific products only. Compounded and "
        "unapproved versions are not FDA-approved; verify any exact product on "
        "DailyMed.",
        "https://www.fda.gov/drugs/drug-alerts-and-statements/fdas-concerns-unapproved-glp-1-drugs-used-weight-loss",
        "verified", "fda",
    ),
    (
        "BPC-157",
        "Research peptide",
        "not-fda-approved",
        "No FDA-approved human product exists for this ingredient; appears in "
        "FDA compounding discussions. See the FDA human drug compounding page.",
        "https://www.fda.gov/drugs/human-drug-compounding",
        "verified", "fda",
    ),
    (
        "TB-500 (Thymosin beta-4)",
        "Research peptide",
        "not-fda-approved",
        "No FDA-approved human product exists for this ingredient. See the FDA "
        "human drug compounding page.",
        "https://www.fda.gov/drugs/human-drug-compounding",
        "verified", "fda",
    ),
    (
        "CJC-1295",
        "Research peptide",
        "not-fda-approved",
        "No FDA-approved human product exists for this ingredient. See the FDA "
        "human drug compounding page.",
        "https://www.fda.gov/drugs/human-drug-compounding",
        "verified", "fda",
    ),
    (
        "Ipamorelin",
        "Research peptide",
        "not-fda-approved",
        "No FDA-approved human product exists for this ingredient. See the FDA "
        "human drug compounding page.",
        "https://www.fda.gov/drugs/human-drug-compounding",
        "verified", "fda",
    ),
    (
        "Compounded GLP-1 copies",
        "Compounded copy category",
        "compounding-flagged",
        "FDA has published guidance and risk context on compounded GLP-1 "
        "copies. Verify current FDA position directly.",
        "https://www.fda.gov/drugs/human-drug-compounding",
        "verified", "fda",
    ),
    # ---- Expanded candidates (sourced; regulatory status only) ----
    (
        "Somatropin (HGH)",
        "Growth hormone (ingredient)",
        "fda-approved",
        "Approved products exist for this ingredient (e.g., Genotropin, "
        "Norditropin, Skytrofa). MedlinePlus identifies somatropin as a human "
        "growth hormone analog used for specific growth-hormone-related and "
        "other medical conditions — it is not a general height or appearance "
        "enhancer. Height/growth context: approval covers those labeled "
        "indications in specific products only — use for 'height enhancement' "
        "outside them is not FDA-approved. This app takes no position on "
        "personal use; verify the exact product and its labeled indications "
        "on DailyMed.",
        "https://medlineplus.gov/druginfo/meds/a622022.html",
        "verified", "medlineplus",
    ),
    (
        "Tesamorelin",
        "GHRH analog (ingredient)",
        "fda-approved",
        "Approved products exist for this ingredient (e.g., Egrifta). "
        "MedlinePlus: used for excess abdominal fat in adults with "
        "HIV-associated lipodystrophy; the reference specifically says it is "
        "not used for weight loss. Approval applies to those specific products "
        "and indications only. Check approval in Drugs@FDA; labeling on DailyMed.",
        "https://medlineplus.gov/druginfo/meds/a611035.html",
        "verified", "medlineplus",
    ),
    (
        "Setmelanotide",
        "MC4R agonist (ingredient)",
        "fda-approved",
        "Approved products exist for this ingredient (e.g., Imcivree) with "
        "labeled use in specific rare genetic obesity conditions. Approval "
        "applies to those specific products and indications only. Verify on "
        "DailyMed.",
        "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=setmelanotide",
        "verified", "dailymed",
    ),
    (
        "Bremelanotide (PT-141)",
        "Melanocortin agonist (ingredient)",
        "fda-approved",
        "Approved products exist for this ingredient (e.g., Vyleesi) with a "
        "labeled indication for specific patients. Approval applies to those "
        "specific products and indications only. Check approval in Drugs@FDA; labeling on DailyMed.",
        "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=bremelanotide",
        "verified", "dailymed",
    ),
    (
        "Liraglutide",
        "GLP-1 receptor agonist (ingredient)",
        "fda-approved",
        "Approved products exist for this ingredient (e.g., Victoza, Saxenda) "
        "— approval applies to those specific products only. MedlinePlus "
        "covers particular diabetes, cardiovascular-risk, and "
        "weight-management uses; exact product and patient context matter. "
        "FDA has raised concerns about unapproved GLP-1 versions; verify any "
        "exact product on DailyMed.",
        "https://medlineplus.gov/druginfo/meds/a611003.html",
        "verified", "medlineplus",
    ),
    (
        "Dulaglutide",
        "GLP-1 receptor agonist (ingredient)",
        "fda-approved",
        "Approved products exist for this ingredient (e.g., Trulicity). "
        "MedlinePlus covers type 2 diabetes and cardiovascular-risk reduction "
        "in specified populations. Approval applies to those specific products "
        "and indications only. Check approval in Drugs@FDA; labeling on DailyMed.",
        "https://medlineplus.gov/druginfo/meds/a614047.html",
        "verified", "medlineplus",
    ),
    (
        "Teriparatide",
        "PTH analog (ingredient)",
        "fda-approved",
        "Approved products exist for this ingredient (e.g., Forteo). "
        "MedlinePlus: an osteoporosis treatment — not a general height-growth "
        "entry. Approval applies to those specific products and indications "
        "only. Check approval in Drugs@FDA; labeling on DailyMed.",
        "https://medlineplus.gov/druginfo/meds/a603018.html",
        "verified", "medlineplus",
    ),
    (
        "Abaloparatide",
        "PTHrP analog (ingredient)",
        "fda-approved",
        "Approved products exist for this ingredient (e.g., Tymlos). "
        "MedlinePlus: an osteoporosis treatment; bone-treatment information "
        "must not be extrapolated into claims about height or appearance. "
        "Approval applies to those specific products and indications only. "
        "Check approval in Drugs@FDA; labeling on DailyMed.",
        "https://medlineplus.gov/druginfo/meds/a617038.html",
        "verified", "medlineplus",
    ),
    (
        "GHK-Cu",
        "Copper peptide (bulk substance)",
        "compounding-flagged",
        "FDA documents concerns for compounded injectable GHK-Cu, including "
        "immunogenicity (aggregation, peptide-related impurities) and limited "
        "human safety data; this concern is specific to injectable routes — "
        "non-injectable GHK-Cu is evaluated separately on FDA's 503A category "
        "list. Not an FDA-approved ingredient for any drug product.",
        "https://www.fda.gov/drugs/human-drug-compounding/certain-bulk-drug-substances-use-compounding-may-present-significant-safety-risks",
        "verified", "fda",
    ),
    (
        "AOD-9604",
        "hGH fragment (bulk substance)",
        "compounding-flagged",
        "FDA's withdrawn-nomination record identifies limited safety "
        "information, immunogenicity/characterization concerns, and serious "
        "adverse events with uncertain causality. This is nomination/category "
        "context, not an approval or a safety clearance, and the nomination "
        "was withdrawn.",
        "https://www.fda.gov/drugs/human-drug-compounding/certain-bulk-drug-substances-use-compounding-may-present-significant-safety-risks",
        "verified", "fda",
    ),
    (
        "Thymosin-alpha 1",
        "Immune-modulating peptide (bulk substance)",
        "compounding-flagged",
        "FDA's withdrawn-nomination record identifies inadequate safety "
        "information and potential immunogenicity/characterization concerns "
        "for proposed compounded use. Nomination/category context only — not "
        "an approval or a safety clearance, and the nomination was withdrawn.",
        "https://www.fda.gov/drugs/human-drug-compounding/certain-bulk-drug-substances-use-compounding-may-present-significant-safety-risks",
        "verified", "fda",
    ),
    (
        "Sermorelin",
        "GHRH analog (ingredient)",
        "unknown",
        "Regulatory status not established here: a somatropin-stimulating "
        "product was formerly marketed, but current US market and FDA status "
        "for this ingredient is not confirmed in this app's data. Verify "
        "directly before relying on any status.",
        "https://www.fda.gov/drugs/human-drug-compounding",
        "awaiting-verification", "fda",
    ),
    (
        "Ibutamoren (MK-677)",
        "Investigational compound (bulk substance)",
        "not-fda-approved",
        "No FDA-approved human product exists for this ingredient. FDA places "
        "ibutamoren mesylate in category 2 (significant safety risks) for "
        "compounding, citing the potential for congestive heart failure in "
        "certain patients — a randomized trial in hip-fracture recovery was "
        "terminated early over a congestive-heart-failure safety signal. Read "
        "FDA's page directly.",
        "https://www.fda.gov/drugs/human-drug-compounding/certain-bulk-drug-substances-use-compounding-may-present-significant-safety-risks",
        "verified", "fda",
    ),
    (
        "Melanotan II",
        "Unapproved tanning product category",
        "not-fda-approved",
        "No FDA-approved product exists for this ingredient; unapproved "
        "tanning-injection products have been the subject of public-health "
        "warnings. Risk context and current status need verification against "
        "FDA sources.",
        "https://www.fda.gov/drugs/human-drug-compounding",
        "awaiting-verification", "fda",
    ),
]

BRAND_ROWS = [
    # (name, supplier_type, region, notes, is_demo)
    ("Demo Brand A", "pharma", "US", "Synthetic demo entry. Verify any real "
     "seller yourself via the check links.", 1),
    ("Demo Brand B", "compounding-pharmacy", "US", "Synthetic demo entry. "
     "Compounded products are not FDA-approved; use the FDA checklist.", 1),
    ("Demo Brand C", "research-supplier", "Unspecified", "Synthetic demo "
     "entry. Research suppliers are not licensed to sell drugs for human "
     "use.", 1),
]

USAGE_DEMO_ROWS = [
    # (peptide_name, amount, unit, route, taken_at, notes)
    ("Semaglutide", 0.25, "mg", "unspecified",
     "2026-11-01T09:00:00", "Demo row — recorded by user, not suggested by app."),
    ("BPC-157", 250, "mcg", "unspecified",
     "2026-11-02T10:30:00", "Demo row — synthetic data for the demo profile."),
    ("BPC-157", 250, "mcg", "unspecified",
     "2026-11-05T10:30:00", "Demo row — synthetic data for the demo profile."),
]

SYMPTOM_DEMO_ROWS = [
    ("BPC-157", 2, "Mild redness at site (demo data)",
     "2026-11-05T11:00:00"),
    ("Semaglutide", 3, "Nausea after evening meal (demo data)",
     "2026-11-02T19:30:00"),
]

REMINDER_DEMO_ROWS = [
    ("Semaglutide", "09:00", "Mon,Fri", "Demo reminder set by the user.", 1),
    ("BPC-157", "10:30", "Mon,Tue,Wed,Thu,Fri", "Demo reminder set by the user.", 0),
]

# Reviewed aliases: searching an alias resolves to the canonical entry and the
# UI explains the relationship (spec: "Searching 'HGH' should explain the
# relationship to somatropin and offer selection, not silently substitute").
# Edited data-driven here, applied via UPDATE in seed_demo — never renamed
# under existing historical logs.
CATALOG_ALIASES = {
    "Somatropin (HGH)": ["HGH", "human growth hormone", "growth hormone", "GH"],
    "Ibutamoren (MK-677)": ["MK-677", "ibutamoren mesylate"],
    "TB-500 (Thymosin beta-4)": ["thymosin beta-4", "TB500"],
    "Thymosin-alpha 1": ["thymosin alpha 1", "Ta1", "thymalfasin"],
    "Bremelanotide (PT-141)": ["PT-141"],
}

# Pramlintide and exenatide are deliberately NOT imported as available options
# (spec: MedlinePlus reports US discontinuation of pramlintide and exenatide
# brands no longer on the market). If added later, they belong in a reviewed
# historical/availability-sensitive workflow distinguishing ingredient
# existence, approval history, and current marketing status.


def refresh_catalog(conn):
    """Data-driven catalog migration (spec: edits via migrations, not UI arrays).

    Updates/inserts the reviewed reference rows in place, keeping stable row
    IDs. Never touches user-owned tables or historical logs.
    """
    cur = conn.cursor()
    for (name, category, regulatory_status, evidence_note, source_url,
         review_status, source_type) in CATALOG_ROWS:
        row = cur.execute("SELECT id FROM catalog WHERE name = ?", (name,)).fetchone()
        if row:
            cur.execute(
                "UPDATE catalog SET category=?, regulatory_status=?, "
                "evidence_note=?, source_url=?, review_status=?, source_type=?, "
                "last_reviewed=date('now') WHERE id=?",
                (category, regulatory_status, evidence_note, source_url,
                 review_status, source_type, row["id"]),
            )
        else:
            cur.execute(
                "INSERT INTO catalog (name, category, regulatory_status, "
                "evidence_note, source_url, review_status, source_type, "
                "last_reviewed) VALUES (?, ?, ?, ?, ?, ?, ?, date('now'))",
                (name, category, regulatory_status, evidence_note, source_url,
                 review_status, source_type),
            )
    for name, aliases in CATALOG_ALIASES.items():
        cur.execute(
            "UPDATE catalog SET aliases = ? WHERE name = ?",
            (json.dumps(aliases), name),
        )


def seed_demo(db_path):
    """Create schema and insert synthetic demo data for the demo user."""
    init_db(db_path)
    from .db import connect
    conn = connect(db_path)
    cur = conn.cursor()

    refresh_catalog(conn)
    cur.executemany(
        "INSERT OR IGNORE INTO brands (name, supplier_type, region, notes, is_demo) "
        "VALUES (?, ?, ?, ?, ?)",
        BRAND_ROWS,
    )

    cur.execute("SELECT id FROM users WHERE display_name = 'Demo User'")
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "INSERT INTO users (display_name, is_demo) VALUES ('Demo User', 1)"
        )
        demo_user_id = cur.lastrowid
    else:
        demo_user_id = row["id"]
        # Reset: clear any existing synthetic rows for the demo profile so
        # re-seeding produces a clean, predictable sample dataset.
        cur.execute("DELETE FROM usage_log WHERE user_id = ?", (demo_user_id,))
        cur.execute("DELETE FROM symptoms WHERE user_id = ?", (demo_user_id,))
        cur.execute("DELETE FROM reminders WHERE user_id = ?", (demo_user_id,))
        cur.execute("DELETE FROM observations WHERE user_id = ?", (demo_user_id,))

    brand_a = cur.execute(
        "SELECT id FROM brands WHERE name = 'Demo Brand A'"
    ).fetchone()["id"]

    cur.executemany(
        "INSERT INTO usage_log (user_id, peptide_name, amount, unit, route, "
        "brand_id, taken_at, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(demo_user_id, *r[:4], brand_a, *r[4:]) for r in USAGE_DEMO_ROWS],
    )
    cur.executemany(
        "INSERT INTO symptoms (user_id, peptide_name, severity, description, "
        "logged_at) VALUES (?, ?, ?, ?, ?)",
        [(demo_user_id, *r) for r in SYMPTOM_DEMO_ROWS],
    )
    cur.executemany(
        "INSERT INTO reminders (user_id, peptide_name, time_of_day, days, "
        "notes, enabled) VALUES (?, ?, ?, ?, ?, ?)",
        [(demo_user_id, *r) for r in REMINDER_DEMO_ROWS],
    )

    conn.commit()
    conn.close()
    return demo_user_id
