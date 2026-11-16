# OpenCode update: broader catalog and personal tracking goals

> Transcribed from the user's original specification PDF
> (`OpenCode update  broader catalog and personal tracking goals.pdf`).
> This is the source of truth; the previous file at this path was a
> missing-document status stub (backed up at `docs/archive/`).

Apply this update to the existing app without rebuilding it. Preserve its
tracking, reminder, export, privacy, and safety requirements; this update
expands what users can record, not what the app recommends they take.

Add more catalog entries and optional reasons for tracking. Separate "what I
hope to achieve" from "what this medication is indicated for" and from "what the
evidence shows."

Do not categorize substances as "for looks," "for height," or "for ascending."
Instead, let users privately record goals such as appearance or body composition
without promising that their chosen substance will achieve them.

## Product decision

### Expand the catalog in reviewed batches

Inspect the current catalog and deduplicate before adding entries. The following
are candidates, not a claim that they are absent from the current application,
available for purchase, appropriate for a user, or approved in every
formulation.

Use a section name such as "Peptides & related medications" if the scope
includes growth-hormone medicines. Include generic and exact product records
separately, with stable identifiers, aliases, formulation/route, jurisdiction,
reference URLs, reviewed date, and explicit unknowns.

### Candidate additions and supporting references

| Candidate | Reference context, not a recommendation |
| --- | --- |
| Somatropin | A human growth hormone analog used for specific growth-hormone-related and other medical conditions; do not present it as a general height or appearance enhancer. (MedlinePlus) |
| Tesamorelin | Used for excess abdominal fat in adults with HIV-associated lipodystrophy; the reference specifically says it is not used for weight loss. (MedlinePlus) |
| Liraglutide | Its reference covers particular diabetes, cardiovascular-risk, and weight-management uses; exact product and patient context matter. (MedlinePlus) |
| Dulaglutide | Its reference covers type 2 diabetes and cardiovascular-risk reduction in specified populations. (MedlinePlus) |
| Teriparatide | An osteoporosis treatment, not a general height-growth entry. (MedlinePlus) |
| Abaloparatide | An osteoporosis treatment; avoid extrapolating bone-treatment information into claims about height or appearance. (MedlinePlus) |
| GHK-Cu | FDA identifies concerns for compounded injectable GHK-Cu, including immunogenicity and limited human safety data; preserve the injectable-route qualification. (FDA) |
| AOD-9604 | FDA identifies limited safety information, immunogenicity/characterization concerns, and serious events with uncertain causality. (FDA) |
| Thymosin-alpha 1 | FDA identifies inadequate safety information and potential immunogenicity/characterization concerns for proposed compounded use. (FDA) |

These references support candidate identity and context, not a live
approval/availability determination. For the FDA bulk-substance entries, retain
the source's nomination/category context and do not turn a withdrawn
nomination into an approval or safety clearance.

### Historical and availability-sensitive records

Support historical logging without pretending every record is currently
marketed. MedlinePlus reports US discontinuation of pramlintide and flags listed
exenatide brands as no longer on the market, so do not import either as an
automatically available purchase option. (Pramlintide reference, exenatide
reference)

Keep these records in a reviewed historical/availability-sensitive workflow if
added. Distinguish ingredient existence, approval history, current marketing
status, and actual availability.

## Catalog behavior

- Search canonical names, reviewed aliases, and exact product names. Searching
  "HGH" should explain the relationship to somatropin and offer selection, not
  silently substitute a product or formulation. Somatropin is identified as an
  hGH analog in its reference. (MedlinePlus)
- Keep injectable and topical formulations separate. Never transfer
  route-specific safety statements across routes without supporting evidence.
- Do not merge similarly named compounds or variants solely because a vendor
  uses them interchangeably.
- Preserve custom/unlisted entries and the user's original label text.
- Sort by personal saved products, recent use, or alphabetically, not
  popularity or goal-based recommendations.
- Do not pad the catalog with invented variants to reach a target count.
- Make edits data-driven through migrations/import files and a review workflow,
  not repeated hardcoded UI arrays.
- Preserve stable IDs and historical logs when adding, renaming, merging, or
  retiring catalog records.

## Add "What would you like to track?"

- Use optional multi-select chips during onboarding, editable later in
  Settings. Allow Skip and Custom reason; do not require users to disclose a
  medical condition or an appearance concern.
- Suggested labels:
  - Prescribed treatment and medication routine
  - Symptoms and side effects
  - Weight or body-composition observations
  - Training and recovery observations
  - Skin or hair observations
  - Sleep and energy observations
  - Appearance-related personal goals
  - Clinician-managed growth or hormone treatment
  - Preparing records for a healthcare visit
  - General recordkeeping
  - Custom reason
- These are user motivations, not treatment indications or promises. Display a
  concise explanation: "Your goals customize your journal, not medication
  recommendations. Recording a goal does not mean a product is effective or
  appropriate for it."
- Permit neutral custom wording without shaming or endorsing it. Do not use
  "ascend," attractiveness rankings, facial scores, body comparisons, or "fix
  your flaws" language in product copy.

### Make goals useful without making them prescriptions

- Offer optional journal fields based on the selected goal, with a preview and
  user confirmation:
  - Weight/body composition: manually entered weight with units and optional
    waist measurement.
  - Training/recovery: activity notes, subjective soreness, and perceived
    recovery.
  - Skin/hair: text observations; defer photos until explicit consent, private
    storage, deletion, and export are designed and tested.
  - Sleep/energy: user-entered sleep duration and subjective energy.
  - Prescribed treatment: user-entered treatment context and questions for the
    next visit.
  - Appearance: private notes about the user's own goals, without
    attractiveness ratings, social comparison, or inferred defects.
  - Clinician-managed growth/hormone treatment: optional user-recorded
    measurements and visit notes, without predicted height gains or
    growth-potential scoring.
- All fields are optional. Selecting a goal must never select a peptide,
  prefill a dose, recommend a stack, change a schedule, produce a brand
  ranking, or hide relevant warnings.
- Charts show recorded observations, missing data, and units. They must not
  claim that a product caused a change or calculate a "peptide effectiveness"
  score.

## HGH and height: required guardrail

- HGH does not increase height after growth plates have fused; synthetic HGH
  also carries health risks including swelling, joint/muscle pain, and insulin
  resistance. (Cleveland Clinic)
- When a user explicitly selects a height-related goal or searches HGH, show a
  short, sourced educational note. Suggested text:
  > "Growth hormone is not a general height enhancer. Once growth plates have
  > fused, HGH does not increase height. This app cannot assess growth
  > potential or recommend hormone treatment. Discuss growth concerns with a
  > qualified clinician."
- Link that note to the reviewed reference above. Do not infer growth-plate
  status from age, height, a photo, or other app data.
- Maintain the existing adult-only scope. Do not add pediatric hormone
  optimization, dosing, height predictions, or parent/child treatment workflows
  as part of this update; any future pediatric product requires a separate
  clinician-led and privacy-reviewed design.
- Do not imply the concern is merely regulatory or that adding a disclaimer
  makes an enhancement recommendation acceptable. Keep the entire feature about
  documentation and education.

## Data model and privacy

- Add stable tracking_goal identifiers and a user-owned association table, with
  optional private custom text. Store suggested journal fields separately from
  medical claims and product indications.
- Changing a goal must not delete historical observations or alter medication
  records. Make journal customization reversible, and include goals in export
  and deletion flows.
- Treat appearance concerns, health goals, and notes as sensitive user data. Do
  not send them to advertising, analytics payloads, public profiles, or
  external AI by default.

## Acceptance criteria

1. Existing records still resolve after catalog expansion; duplicate names and
   aliases do not create duplicate substances.
2. New entries include source and review metadata; unknown approval/availability
   fields stay unknown.
3. Research-compound entries can be logged without purchase links,
   endorsements, dose defaults, or implied benefits.
4. Goals are optional, multi-select, editable, and exportable/deletable.
5. Selecting "Appearance-related personal goals" changes only optional journal
   fields, not product rankings or treatment advice.
6. Selecting a height-related goal or HGH displays the reviewed note without
   estimating growth potential.
7. Clinical indications remain visibly separate from the user's goals.
8. Goal changes preserve existing logs and measurements.
9. Custom goal text is safely rendered and protected by the same ownership
   checks as other health records.
10. No "safe," "proven for your goal," or effectiveness score appears merely
    because a product and goal coexist.

Implement the catalog schema/import changes and goal selector first, then
optional journal customization. Run the existing tests and new regression
tests; report verified entries, unresolved source/availability questions,
changed files, and exact test results.
