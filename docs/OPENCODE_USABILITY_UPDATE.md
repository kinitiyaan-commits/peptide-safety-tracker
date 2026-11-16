# OpenCode update: make the peptide tracker useful for real users

> Transcribed from the user's original specification PDF
> (`OpenCode update  make the peptide tracker useful for real users.pdf`).
> This is the source of truth; the previous file at this path was a
> missing-document status stub (backed up at `docs/archive/`).

Apply this feedback to the existing app, not a fresh rewrite. Keep the improved
Today / History / Learn / Settings layout and slide-up logging form. Read the
existing project instructions and peptide resource guide first, then inspect the
implementation before editing.

The goal is an effective recordkeeping tool people can use consistently, not a
tool that claims to make peptide use safe or effective. Prioritize accurate
records, low-friction logging, reliable reminders, useful exports, and honest
uncertainty.

## Build first: a searchable peptide dropdown

Replace repeated free-text peptide fields with one accessible, reusable
searchable combobox across usage logging, symptom logging, reminders, and
product setup.

- **Search:** Match canonical names and reviewed aliases. Show the canonical
  name after selection, with an optional plain-language formulation or product
  subtitle.
- **Personal shortcuts:** Put "My saved products" and "Recently logged" first.
  These reflect the user's own records, not popularity or clinical
  recommendations.
- **Catalog:** Provide a small, reviewed reference list. Do not invent medical
  claims or seed real product details from model memory.
- **Custom entry:** Include "Add an unlisted product." Label it user-entered and
  unverified; do not reject a record merely because the product is absent from
  the catalog.
- **Product distinction:** An ingredient selection must not silently choose a
  brand, route, strength, or formulation. Let users choose an existing personal
  product or save the exact product details they know.
- **Unknowns:** Permit unknown brand/formulation details without guessing. Do
  not require excessive metadata just to record an event.
- **Interaction:** Support keyboard navigation, screen-reader labels, touch
  selection, clear/reset, empty search results, and a visible selected state.
- **Safety:** No "recommended for you," trending peptide lists, default doses,
  stack suggestions, or globally "safe" badges.
- Use the same underlying product IDs everywhere so spelling differences do not
  split history into separate substances. Preserve original names on historical
  entries when a catalog name changes.

## Build first: make logging fast and dependable

- **Time:** Default a new administration event to the current local date and
  time. Show "Now" with a Change option; use separate date and time controls
  when editing.
- **Future entries:** Keep actual administration separate from planned
  reminders. Do not save a future event as already taken.
- **Validation:** Replace browser-only invalid-date messages with inline
  guidance, and preserve all entered values after an error.
- **Amounts:** Require an explicit amount and unit. Never suggest a dose,
  silently convert units, or reuse a prior amount without deliberate user
  action and confirmation.
- **Confirmation:** After save, show the product and timestamp, such as "Saved
  for Nov 2, 11:09 PM," with "View entry" and Undo.
- **History edits:** Let users view, correct, and delete their own entries.
  Explain and test how corrections are recorded.
- **Duplicates:** Prevent double-submit duplicates and prompt on likely
  duplicate entries without blocking an intentional override.
- **Visual polish:** Replace missing-character icons with SVGs, add persistent
  field labels, improve small text, and make the center navigation action
  clearly mean "Log use."
- Avoid making a user complete a long onboarding form before recording their
  first entry. Age and tracking goals should remain optional unless a reviewed
  requirement makes them necessary.

## Build next: personal products and reminders

### My products

Give users a reusable list of the products they actually track. Each record can
include display name, catalog link, exact formulation, manufacturer or
pharmacy, label strength, optional lot, user-entered expiration, and notes.

Keep label strength distinct from an administered amount. Allow archiving
without erasing history, and do not calculate doses or invent storage
instructions or beyond-use dates.

### Reliable reminders

- Replace the free-text weekday field with weekday chips and an Every day
  option.
- Link reminders to a saved product and a user-selected time.
- Support pause, resume, snooze, skip, and cancel.
- Tapping "Log use" from a reminder opens a prefilled product context, but never
  automatically records administration or assumes the amount.
- Distinguish "Not logged" from "Missed dose." Lack of an entry does not prove
  the user did not take something.
- Define and test timezone, daylight-saving, duplicate-job, and
  permission-denied behavior.
- Show notification permission and delivery status, offer a test notification,
  and keep lock-screen text generic by default.
- Verify whether reminders work with the app closed on the target devices. If
  they do not, label them in-app-only rather than pretending background
  notifications work.
- Never give catch-up or missed-dose treatment instructions.
- Put upcoming reminders and a shortcut to recent products on Today. Keep
  administrative settings and long educational content off that screen.

## Build next: history people can actually use

- **Timeline and calendar:** Browse actual logs, symptom observations, and
  reminder states without conflating them.
- **Filters:** Filter by product, date range, and event type.
- **Symptoms:** Offer optional common observation labels plus custom text, an
  understandable subjective severity scale, timing, and notes. Do not require
  the user to attribute a symptom to a peptide.
- **Simple trends:** Show recorded symptoms over time and user-entered
  measurements with explicit units and gaps. Do not claim that a peptide caused
  an improvement or reaction, or that the chart measures treatment
  effectiveness.
- **Visit summary:** Generate a readable, printable summary for a selected date
  range with products, actual logs, observations, and notes. Include
  corrections and distinguish user-entered facts from sourced reference
  information.
- **Exports:** Retain CSV/JSON export and test the contents, ownership rules,
  readable dates, units, and safe handling of free text.
- Do not add streaks, leaderboards, or rewards for taking more or continuing
  use. The useful outcome is accurate records, not maximum consumption.

## Keep education and comparison trustworthy

- Make Learn searchable, with short expandable explanations and source/review
  dates. Avoid replacing a usable interface with walls of disclaimers; keep a
  concise scope notice and contextual warnings.
- Compare documented product and pharmacy attributes, not "best peptide for
  your goals." Keep ingredient, exact product, manufacturer, pharmacy, approval
  evidence, and verification status separate.
- Use Drugs@FDA for approval verification and DailyMed for labeling, following
  the resource guide. DailyMed includes labeling for products that are not
  FDA-approved, so do not imply that finding an entry establishes approval.
  (DailyMed scope)
- Keep research-use products out of purchase recommendations. Allow neutral
  personal logging without turning it into endorsement, and never infer safety
  from a certificate, purity number, missing warning, or empty search result.

## Match privacy claims to the actual architecture

First determine whether this is a single-device local app or a hosted
multi-user service. Document the actual architecture and implement the matching
protections rather than adding reassuring copy.

- **Local mode:** Explain where records reside, how to back up and restore
  them, what deletion does, and whether anyone using the device can switch
  profiles. Profile separation is not authentication.
- **Hosted mode:** Add real authentication, server-side ownership checks,
  secure sessions, private storage, and tested cross-user isolation before
  accepting real health records. A server-side database is not "stored only on
  your device."
- **Privacy:** Verify claims about network traffic, analytics, storage,
  encryption configuration, and external AI use. Do not claim absolute privacy
  or compliance without evidence.
- **Data control:** Provide account/profile deletion, export, and tested
  restore where supported. Explain backup-retention limitations.
- **Offline behavior:** Show explicit saved, pending, failed, and retry states.
  Do not claim offline support until tested; never silently lose or duplicate a
  log during reconnect.
- **Device checks:** Test mobile widths, keyboard-open sheets, scrolling,
  focus, touch targets, and screen-reader labels.
- **Review gate:** Use synthetic data until security, privacy, clinical-content,
  and applicable regulatory reviews are complete.
- Do not build cloud sync, an AI coach, a marketplace, or lab interpretation
  merely to make the feature list larger. Every new feature must solve a
  demonstrated user problem.

## Required before inviting real users

### Acceptance criteria and usability validation

Before calling this iteration finished, demonstrate:

1. Searching an alias finds the canonical peptide; selecting it populates the
   same product identity across logs and reminders.
2. An unlisted product can be saved without receiving an approval or safety
   badge.
3. A new entry defaults to now, accepts a valid backdated timestamp, and gives
   a clear confirmation.
4. Invalid input preserves the form and identifies the field requiring
   correction.
5. Repeated taps, reconnects, and retries do not create unintended duplicate
   records.
6. Editing or archiving a product does not rewrite historical administered
   amounts.
7. A reminder never marks an administration completed without explicit user
   input.
8. A paused or deleted reminder cannot leave an active scheduled notification
   behind.
9. Exported data matches the selected user, dates, products, amounts, and
   units.
10. A second user cannot access another user's records through direct
    endpoints, not just through the UI.
11. Permission denial, network failures, empty states, and source outages have
    understandable behavior.
12. All visible privacy and notification claims match tested implementation.

After implementation, propose a small usability test with five consenting
adults using synthetic records. Have them create a product, log an event,
backdate it, edit it, configure a reminder, and export a visit summary; observe
failures rather than assuming the redesign works.

Suggested initial usability target: at least four of five testers complete the
logging task unassisted, and a returning user logs an event within about 20
seconds. These are proposed targets, not measured results or clinical-outcome
claims.

## Implementation order and reporting

Implement in small, working slices:

1. Searchable dropdown, date/time fixes, reliable save feedback, and icons.
2. Saved products, useful history, and edit/export flows.
3. Reminders with verified delivery behavior.
4. Architecture-appropriate privacy/security and private-beta launch checks.

Run the existing test suite and add regression tests for each slice. Report
files changed, exact test results, working versus mocked behavior, remaining
blockers, and manual checks needed on real devices.

Start implementing the first slice now. Preserve the current app and do not
deploy publicly, collect real health records, or contact testers without
explicit approval.
