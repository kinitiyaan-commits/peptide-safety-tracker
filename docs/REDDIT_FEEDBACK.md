# Beta feedback preview: before you share

This is a prototype for usability feedback, not a medical tool or production
release. The repository's project constraints allow synthetic demo data only
until a privacy and security review is complete. **Ask testers not to enter
real health information.**

## Preview without touching production

- Keep beta changes on `feature/beta-now`; do not merge them into `main` to
  create a preview.
- For a separate hosted preview, deploy only the `pwa/` directory to a
  separate preview site (for example, a new Netlify site). Do not change the
  GitHub Pages source setting unless you intentionally want to change the
  existing production deployment arrangement.
- The existing Pages workflow deploys `pwa/` from pushes to `main`. Switching
  Pages to the `pages-beta` branch can leave production updates out of sync
  until that branch is deliberately refreshed.
- Before sharing, open the preview in a private/incognito window and confirm
  the URL, BETA label, links, layout, and behavior. Use only synthetic entries
  while testing. Remember the service worker may cache a previous build; use a
  fresh browser profile or clear that preview site's data when checking an
  update.

## Claims to avoid in a Reddit post

Do not describe the app as catching mistakes, preventing an extra dose, or
making dose entry safe. It can display information such as a prior same-product
entry or a unit conversion, but those are not clinical checks, do not validate
what a person took, and cannot guarantee that an error will be caught. Describe
features neutrally as things the prototype displays or records.

Do not claim that "no data leaves the device" without qualification. Journal
records are stored in browser storage and the app does not send journal records
to its own server, but the hosting provider receives ordinary web requests
(including IP address/server logs). If a tester chooses an external regulatory
link, the destination site receives that request and may see the search term.

## Suggested Reddit copy

> **I’m testing a beta prototype of a local-first peptide journal — feedback wanted**
>
> I’ve been building a small browser-based journal prototype and would value
> feedback on what is confusing, useful, or unnecessary. This is a usability
> preview, not medical advice, and it does not recommend doses or rate products
> or sellers.
>
> The app can record user-entered journal entries, symptoms, and observations;
> it also displays sourced regulatory references and links to official sources.
> Records are stored in this browser on this device. The hosting provider may
> receive standard web request information, and external links open the
> selected official site.
>
> **Please use synthetic/demo data only — do not enter real health information
> or post personal health details in the thread.** The prototype has not
> completed a privacy/security review and is not for real health records.
>
> I’d especially appreciate feedback on navigation, wording, accessibility,
> and what feels unclear. Feature displays are not safety checks or guarantees.
> Please check the subreddit’s self-promotion rules before posting.

## Before posting

- Preview the exact URL you plan to share and make sure it is the separate beta,
  not the production root.
- Confirm `privacy.html` and `terms.html` are reachable and decide whether the
  `[OWNER TO SUPPLY]` operator/contact placeholders must be completed before
  public sharing. Do not invent those values.
- Remove screenshots or screen recordings that show personal details. Do not
  ask commenters to share health records; request usability feedback instead.
- Check the target subreddit rules and disclose that you made the project.
- Test the final branch after any changes: `.venv/bin/python -m pytest tests/ -q`.
