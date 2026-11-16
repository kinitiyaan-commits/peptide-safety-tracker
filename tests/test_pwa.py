"""Static PWA checks for pwa/ (the installable, fully client-side app).

The PWA has no Python runtime, so these are file/structure checks:
- app shell files exist, manifest is valid JSON with required members,
- service worker has cache + fetch + offline fallback,
- storage is browser-side (IndexedDB) and there is NO fetch() of user data,
- icons exist at the required sizes,
- no personal names or absolute machine paths leak into the deliverable.
"""

import json
import re
import struct
import zlib
from pathlib import Path

import pytest

PWA = Path(__file__).resolve().parent.parent / "pwa"
ROOT = PWA.parent


# ------------------------------------------------------------- shell ----

class TestAppShell:
    def test_required_files_exist(self):
        for name in ("index.html", "app.js", "store.js", "data.js",
                     "sw.js", "manifest.webmanifest",
                     "icons/icon-192.png", "icons/icon-512.png"):
            assert (PWA / name).is_file(), f"missing pwa/{name}"

    def test_relative_paths_for_pages_subpath(self):
        html = (PWA / "index.html").read_text()
        for src in re.findall(r'src="([^"]+)"', html):
            assert not src.startswith("/"), "absolute paths break GitHub Pages subpaths"
        manifest = json.loads((PWA / "manifest.webmanifest").read_text())
        assert manifest["start_url"] == "./"
        assert manifest["scope"] == "./"

    def test_manifest_required_members(self):
        m = json.loads((PWA / "manifest.webmanifest").read_text())
        assert m["display"] == "standalone"
        assert "icons" in m and len(m["icons"]) >= 2
        for icon in m["icons"]:
            assert icon["src"].startswith("icons/")
            assert "maskable" in icon["purpose"]


class TestServiceWorker:
    def test_caches_app_shell_and_serves_offline(self):
        sw = (PWA / "sw.js").read_text()
        assert "addEventListener(\"install\"" in sw
        assert "addEventListener(\"fetch\"" in sw
        assert "./index.html" in sw            # offline navigation fallback

    def test_no_remote_styling_dependency(self):
        """Styling is local and versioned — no CDN runtime dependency."""
        html = (PWA / "index.html").read_text()
        assert "cdn.tailwindcss.com" not in html
        assert "cdn.tailwindcss.com" not in (PWA / "sw.js").read_text()
        assert (PWA / "styles.css").is_file()
        assert '<link rel="stylesheet" href="./styles.css">' in html
        assert re.search(r'Version \d', (PWA / "styles.css").read_text())

    def test_controlled_update_strategy(self):
        """Strict install; no auto-skipWaiting; only own caches deleted."""
        sw = (PWA / "sw.js").read_text()
        install = sw.split("addEventListener(\"install\"", 1)[1].split("addEventListener(\"message\"", 1)[0]
        assert "addAll" in install and "cache.addAll(ASSETS)" in sw
        assert install.count("catch") == 0     # no swallowed asset failures
        # skipWaiting exists ONLY behind the ACCEPT_UPDATE message
        msg = sw.split("addEventListener(\"message\"", 1)[1].split("addEventListener(\"activate\"", 1)[0]
        assert "ACCEPT_UPDATE" in msg and "skipWaiting" in msg
        head = sw.split("addEventListener(\"message\"", 1)[0]
        assert "skipWaiting()" not in head
        act = sw.split("addEventListener(\"activate\"", 1)[1]
        assert "CACHE_PREFIX" in act and "startsWith(CACHE_PREFIX)" in act

    def test_privacy_and_terms_pages_precached(self):
        for name in ("privacy.html", "terms.html"):
            f = (PWA / name)
            assert f.is_file(), f"missing pwa/{name}"
            text = f.read_text()
            assert "OWNER TO SUPPLY" in text       # pending literal values visible
            assert "not medical advice" in text or "Not medical advice" in text or "medical" in text
        sw = (PWA / "sw.js").read_text()
        assert '"./privacy.html"' in sw and '"./terms.html"' in sw

    def test_no_external_api_calls_in_app(self):
        """No server API for user data — storage is IndexedDB only."""
        app = (PWA / "app.js").read_text()
        store = (PWA / "store.js").read_text()
        assert "fetch(" not in store
        # app.js uses no fetch()/XHR/XMLHttpRequest either
        assert "fetch(" not in app
        assert "XMLHttpRequest" not in app
        assert "indexedDB" in store

    def test_store_scopes_by_profile(self):
        store = (PWA / "store.js").read_text()
        assert "profileId" in store
        assert "deleteProfile" in store


class TestIcons:
    @pytest.mark.parametrize("size", [192, 512])
    def test_png_dimensions(self, size):
        data = (PWA / "icons" / f"icon-{size}.png").read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        w, h = struct.unpack(">II", data[16:24])
        assert (w, h) == (size, size)


class TestGeneratedData:
    def test_data_js_is_sourced_catalog_only(self):
        data = (PWA / "data.js").read_text()
        assert "GENERATED by tools/make_static_data.py" in data
        assert "NO user data" in data
        # sample entries present with their sources
        assert "Semaglutide" in data
        assert "BPC-157" in data
        assert "fda.gov" in data or "dailymed" in data

    def test_data_matches_python_seed(self):
        import sys
        repo = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(repo))
        from peptide_safety.seed import CATALOG_ROWS
        data = (PWA / "data.js").read_text()
        for row in CATALOG_ROWS:
            assert row[0] in data  # every catalog name present


# --------------------------------------------------- app requirements ---

class TestAppRequirements:
    def _app(self):
        return (PWA / "app.js").read_text()

    def _html(self):
        return (PWA / "index.html").read_text()

    def test_explicit_units_allowlist(self):
        app = self._app()
        assert 'const UNITS = STATIC_DATA.UNITS' in app
        assert '"mcg"' in app and '"mL"' in app

    def test_blank_forms_on_open(self):
        app = self._app()
        for fn in ("openLogSheet", "openSymptomSheet", "openObservationSheet"):
            body = app.split(f"function {fn}", 1)[1].split("\nfunction ", 1)[0]
            assert "form.reset()" in body, f"{fn} does not reset its form"

    def test_fab_opens_single_chooser(self):
        app = self._app()
        assert 'function openFabChooser' in app
        html = self._html()
        today = html.split('id="sec-today"', 1)[1].split("</section>", 1)[0]
        assert "openLogSheet()" not in today
        assert 'id="fab-chooser"' in html

    def test_no_goal_fields_on_dose_form(self):
        html = self._html()
        log_sheet = html.split('id="log-sheet"', 1)[1].split("<!-- SYMPTOM -->", 1)[0]
        assert "observation-fields" not in log_sheet
        assert 'id="u-goal' not in log_sheet

    def test_correction_history_preserved(self):
        app = self._app()
        assert "corrections" in app
        assert "editedAt" in app and "previous" in app

    def test_reminders_labeled_in_app_only(self):
        html = self._html()
        assert "in-app only" in html

    def test_device_only_storage_stated_in_settings(self):
        html = self._html()
        settings = html.split('id="sec-settings"', 1)[1].split("</section>", 1)[0]
        assert "IndexedDB" in settings
        assert "this device" in settings.lower()
        assert "Clearing" in settings or "clearing" in settings

    def test_export_and_import_with_validation(self):
        app = self._app()
        assert "function exportData" in app
        assert "function validateExport" in app
        assert "function importFile" in app
        assert "Import preview" in app or "import preview" in app.lower()
        assert "replace" in app and "merge" in app

    def test_disclaimer_one_line_plus_learn_more(self):
        html = self._html()
        assert "not medical advice" in html
        assert "Learn more" in html

    def test_six_common_goal_chips(self):
        app = self._app()
        line = next(l for l in app.splitlines()
                    if l.strip().startswith("const COMMON_GOALS"))
        keys = [k.strip() for k in line.split("[", 1)[1].split("]", 1)[0].replace("'", "").split(",") if k.strip()]
        assert len(keys) == 6

    def test_awaiting_verification_distinct(self):
        app = self._app()
        assert "awaiting-verification" in app

    def test_no_personal_names_or_paths(self):
        approved_repo = "github.com/kinitiyaan-commits/peptide-safety-tracker"
        for name in ("index.html", "app.js", "store.js", "data.js", "sw.js"):
            text = (PWA / name).read_text().lower()
            # the approved feedback route (repo URL) is the ONLY allowed
            # occurrence of the account name — strip it before checking
            text = text.replace(approved_repo, "approved-repo-url")
            for marker in ("tiyaan", "jordan", "kinitiyaan", "/home/", "c:\\\\"):
                assert marker not in text


# ------------------------------------- beta backlog "Now" (2026-11-15) ----

class TestExplicitUnits:
    """Backlog 'Now': new products start with 'Choose unit', remembered unit
    per product+profile shown before saving, no unrelated unit carry-over."""

    def _app(self):
        return (PWA / "app.js").read_text()

    def _html(self):
        return (PWA / "index.html").read_text()

    def test_unit_select_starts_empty(self):
        html = self._html()
        assert '<option value="">Choose unit</option>' in html
        # no silent default: the first visible option is not a unit
        select = html.split('id="u-unit"', 1)[1].split("</select>", 1)[0]
        first = select.split("<option", 2)[1]
        assert 'value=""' in first

    def test_save_blocked_without_unit(self):
        app = self._app()
        assert '"Choose a unit' in app

    def test_remembered_unit_per_profile(self):
        store = (PWA / "store.js").read_text()
        assert '"productUnits"' in store
        assert "rememberedUnit" in store and "rememberUnit" in store
        # keyed per profile — never inherited across profiles
        assert 'profileId + "|" + String(name).toLowerCase()' in store

    def test_no_unit_carry_over_on_product_change(self):
        app = self._app()
        assert "onProductChanged" in app
        body = app.split("async function onProductChanged", 1)[1].split("\n}", 1)[0]
        assert '$("#u-unit").value = ""' in body

    def test_amount_and_unit_stay_together(self):
        app = self._app()
        # history renders amount and unit as one pair
        assert "${esc(u.amount)} ${esc(u.unit)}" in app
        assert "esc(u.unit)" in app


class TestRepeatLogging:
    def test_log_again_opens_reviewable_form(self):
        app = (PWA / "app.js").read_text()
        body = app.split("function logAgain", 1)[1].split("\nfunction ", 1)[0]
        assert 'openLogSheet(null)' in body          # opens a form
        assert 'localDT()' in body                   # new time = now
        assert '$("#u-notes").value = ""' in body    # notes not copied
        assert "Review before saving" in app

    def test_repeated_taps_guarded(self):
        app = (PWA / "app.js").read_text()
        assert "guardBusy" in app
        for fn in ("logUsage", "logSymptom", "logObservation"):
            seg = app.split(f"async function {fn}", 1)[1].split("\nasync function ", 1)[0]
            assert "guardBusy" in seg, f"{fn} has no repeated-tap guard"


class TestDataPreservation:
    def test_db_upgrade_only_creates_stores(self):
        store = (PWA / "store.js").read_text()
        assert "Data-preserving upgrade" in store
        assert "createObjectStore" in store
        assert "deleteObjectStore" not in store
        upgrade = store.split("req.onupgradeneeded", 1)[1].split("req.onsuccess", 1)[0]
        assert "deleteDatabase" not in upgrade and ".clear(" not in upgrade

    def test_update_prompt_never_auto_reloads(self):
        app = (PWA / "app.js").read_text()
        assert "update-banner" in app
        assert "updatefound" in app
        # location.reload() exists ONLY inside the controlled update flow:
        # applyUpdate's stale-banner grace reload, the controllerchange
        # success reload, and the controllerchange reload after the user
        # explicitly accepts the storage-failure loss warning.
        assert app.count("location.reload()") == 3
        update_flow = app.split("if (\"serviceWorker\" in navigator)", 1)[1]
        assert update_flow.count("location.reload()") == 3

    def test_import_leaves_data_intact_on_failure(self):
        app = (PWA / "app.js").read_text()
        body = app.split("async function importFile", 1)[1].split("\nasync function runImport", 1)[0]
        # validation happens before anything is written
        assert "showImportPreview" in body
        assert "Store.put" not in body

    def test_backup_time_and_dismissible_reminder(self):
        app = (PWA / "app.js").read_text()
        assert 'setMeta("lastBackupAt"' in app
        assert "backupReminderDismissedAt" in app
        html = (PWA / "index.html").read_text()
        assert 'id="last-backup"' in html
        assert 'id="backup-reminder"' in html


class TestInstallAccessibilityFeedback:
    def test_version_identifier_in_settings(self):
        html = (PWA / "index.html").read_text()
        assert 'id="app-version"' in html
        app = (PWA / "app.js").read_text()
        assert "APP_VERSION" in app

    def test_install_help_and_offline_limits(self):
        html = (PWA / "index.html").read_text()
        settings = html.split('id="sec-settings"', 1)[1].split("</section>", 1)[0]
        assert "Add to Home" in settings
        assert "Offline limitations" in settings

    def test_feedback_route_warns_against_health_data(self):
        html = (PWA / "index.html").read_text()
        settings = html.split('id="sec-settings"', 1)[1].split("</section>", 1)[0]
        assert "Feedback" in settings
        warning = settings.split("Privacy warning", 1)[1].split("</p>", 1)[0]
        assert "include medical records" in warning
        assert "never attaches data to feedback automatically" in settings
        assert "github.com/kinitiyaan-commits/peptide-safety-tracker/issues" in settings
        assert "pending the owner's decision" not in settings   # route approved

    def test_no_auto_attachment_anywhere(self):
        app = (PWA / "app.js").read_text()
        # nothing in the app sends data anywhere — no fetch, no beacon, no sendBeacon
        assert "sendBeacon" not in app
        assert "navigator.send" not in app


class TestCombinedTimeline:
    def test_history_filters_include_date_range(self):
        html = (PWA / "index.html").read_text()
        assert 'id="hist-from"' in html and 'id="hist-to"' in html
        app = (PWA / "app.js").read_text()
        body = app.split("function renderHistory", 1)[1].split("\n// ------", 1)[0]
        assert "inRange" in body

    def test_missing_data_wording_neutral(self):
        app = (PWA / "app.js").read_text()
        assert "No matching entries" in app
        assert "Nothing logged yet" in app


class TestAppointmentSummary:
    def _app(self):
        return (PWA / "app.js").read_text()

    def test_summary_exists_with_date_range_and_preview(self):
        app = self._app()
        html = (PWA / "index.html").read_text()
        for token in ("openSummarySheet", "renderSummaryPreview", "sum-from",
                      "sum-to", "sum-preview", "printSummary", "downloadSummary"):
            assert token in app or token in html, f"missing {token}"
        assert 'id="summary-sheet"' in html

    def test_private_notes_excluded_by_default(self):
        html = (PWA / "index.html").read_text()
        sheet = html.split('id="summary-sheet"', 1)[1].split("</div>\n\n<div id=\"toast\"", 1)[0]
        assert 'id="sum-notes"' in sheet and "checked" not in sheet.split("id=\"sum-notes\"")[1].split(">", 1)[0]
        assert "excluded by default" in sheet

    def test_labeled_user_entered_no_claims(self):
        app = self._app()
        assert "not medical advice" in app
        assert "cause, effect, or treatment effectiveness" in app
        assert "recorded during this period" in app

    def test_nothing_sent_automatically(self):
        app = self._app()
        body = app.split("function printSummary", 1)[1].split("\nfunction downloadSummary", 1)[0]
        assert "window.open" in body          # user-initiated print only
        assert "fetch(" not in body and "sendBeacon" not in body


# ------------------------- pre-Reddit blockers (2026-11-15) ----------------

class TestAtomicImport:
    """Imports are fully validated first, then written in ONE transaction."""

    def _app(self):
        return (PWA / "app.js").read_text()

    def _store(self):
        return (PWA / "store.js").read_text()

    def test_atomic_transaction_helper_exists(self):
        store = self._store()
        assert "importAtomic" in store
        body = store.split("importAtomic(writes, clearStores)", 1)[1].split("},", 1)[0]
        assert 'db.transaction(names, "readwrite")' in body
        assert "t.onabort" in body and "t.onerror" in body
        # no await between queued requests
        assert "await" not in body

    def test_import_revalidates_before_apply(self):
        app = self._app()
        body = app.split("async function runImport", 1)[1].split("\n}", 1)[0]
        assert "validateExport(data)" in body
        assert "importAtomic" in body

    def test_replace_is_atomic_not_wipe_then_write(self):
        app = self._app()
        body = app.split("async function runImport", 1)[1].split("\n}", 1)[0]
        # replace wipes stores INSIDE the same transaction (clearStores),
        # not via wipeAllData() before writing
        assert "clearStores" in body
        assert "wipeAllData" not in body

    def test_strict_validation_limits(self):
        app = self._app()
        assert "IMPORT_ID_RE" in app and "^[A-Za-z0-9_-]{1,64}$" in app
        assert "IMPORT_LIMITS" in app
        assert "2 * 1024 * 1024" in app        # 2 MB file cap in importFile
        assert "Number.isFinite(Number(r.amount))" in app
        assert "validISODate" in app
        # cross-profile id collisions and duplicate profile ids are fatal
        assert "more than one profile" in app
        assert "Duplicate profile id" in app

    def test_schema_2_export_includes_product_units(self):
        app = self._app()
        assert "schema: 2" in app
        assert "productUnits" in app.split("function exportData", 1)[1].split("function validateExport", 1)[0]
        # schema-1 imports rebuild remembered units from most recent usage
        assert 'data.schema === 1' in app and "rememberUnit" in app

    def test_import_preview_sensitivity_note(self):
        app = self._app()
        assert "Sensitivity: this file contains private health notes" in app


class TestNoImportedIdXSS:
    """Record ids from imports must never be interpolated into inline
    handlers — buttons use data-act/data-id with a delegated listener."""

    def _app(self):
        return (PWA / "app.js").read_text()

    def test_delegated_actions_replace_inline_ids(self):
        app = self._app()
        assert "DELEGATED_ACTIONS" in app
        assert 'data-act="log-again" data-id="${esc(u.id)}"' in app
        assert 'data-act="correct-dose"' in app
        assert 'data-act="correct-obs"' in app
        assert 'data-act="toggle-reminder" data-id="${esc(r.id)}"' in app

    def test_no_inline_handlers_interpolate_record_ids(self):
        app = self._app()
        # any onclick="fn('...id...')" pattern is forbidden
        assert not re.search(r"onclick=\"\w+\('\$\{[uo]\.id\}", app)
        assert not re.search(r"onclick=\"\w+\('\$\{r\.id\}", app)

    def test_esc_is_quote_safe_for_attributes(self):
        app = self._app()
        assert "&quot;" in app and "&#39;" in app


class TestStaleUnitLookupGuard:
    def test_async_lookup_checked_against_current_state(self):
        app = (PWA / "app.js").read_text()
        body = app.split("async function onProductChanged", 1)[1].split("\n}", 1)[0]
        assert "unitLookupToken" in app
        assert "token !== unitLookupToken" in body
        assert '$("#u-name").value.trim() !== name' in body


class TestBackupWordingAndSummaryDates:
    def test_last_export_wording_is_honest(self):
        app = (PWA / "app.js").read_text()
        assert "Last export initiated" in app
        assert "verify the downloaded copy" in app or "verify it opens" in app
        assert "Last successful backup" not in app

    def test_reversed_range_rejected_everywhere(self):
        app = (PWA / "app.js").read_text()
        assert "summaryRangeError" in app
        for fn in ("renderSummaryPreview", "printSummary", "downloadSummary"):
            seg = app.split(f"function {fn}", 1)[1].split("\nfunction ", 1)[0]
            assert "summaryRangeError" in seg, f"{fn} does not reject a bad range"

    def test_summary_sensitivity_note_even_without_notes(self):
        app = (PWA / "app.js").read_text()
        assert "Sensitive: this summary can contain health information" in app

    def test_summary_uses_local_calendar_days(self):
        app = (PWA / "app.js").read_text()
        body = app.split("function summaryData", 1)[1].split("function ", 1)[0]
        assert "localDTtoDay" in body
        assert "reversed" in body


class TestAccuratePrivacyWording:
    def _html(self):
        return (PWA / "index.html").read_text()

    def test_no_never_transmits_claims(self):
        html = self._html()
        assert "never transmits anything" not in html
        assert "GitHub receives your IP address" in html
        # external links may include the searched product term
        assert "include the product name you're checking" in html

    def test_no_age_collection(self):
        html = self._html()
        assert "new-profile-age" not in html
        assert "Age (optional)" not in html

    def test_feedback_destination_approved(self):
        html = self._html()
        assert "github.com/kinitiyaan-commits/peptide-safety-tracker/issues" in html
        assert "pending the owner's decision" not in html
        assert "public" in html.split("Privacy warning", 1)[1].split("</p>", 1)[0]

    def test_drugsfda_link_in_verification(self):
        app = (PWA / "app.js").read_text()
        assert "accessdata.fda.gov/scripts/cder/daf" in app
        assert "check approval per exact product" in app
        assert 'data.js' not in "x"  # sanity


# ---------------- correction pass (review of 859a664) ----------------

class TestUpdateTargetsWaitingWorker:
    def test_accept_update_messages_registration_waiting(self):
        app = (PWA / "app.js").read_text()
        assert "_swReg = reg;" in app                      # registration retained
        assert "_swReg.waiting.postMessage" in app

    def test_controllerchange_only_reloads_after_an_update(self):
        app = (PWA / "app.js").read_text()
        seg = app.split("controllerchange", 1)[1].split("});", 1)[0]
        assert "hadController" in app                      # first-install claim ignored
        assert "saveDraftSilently()" in seg                # other tabs keep drafts
        assert "location.reload()" in seg


class TestOnBlockedRegistrationTiming:
    def test_onblocked_assigned_before_first_storage_access(self):
        app = (PWA / "app.js").read_text()
        init_body = app.split("async function init()", 1)[1].split("if (\"serviceWorker\" in navigator)", 1)[0]
        assigned = init_body.index("Store.onBlocked")
        first_real_call = re.search(r"Store\.(?!onBlocked)\w+", init_body)
        assert first_real_call is not None
        assert assigned < first_real_call.start()

    def test_init_failures_are_visible(self):
        app = (PWA / "app.js").read_text()
        boot = app.split("DOMContentLoaded", 1)[1].split("});", 1)[0]
        assert "init().catch" in boot
        assert "could not start" in boot


class TestDraftContextPreserved:
    def test_draft_carries_profile_and_editing_id(self):
        app = (PWA / "app.js").read_text()
        body = app.split("function collectDraft", 1)[1].split("function draftHasContent", 1)[0]
        assert "draft.profileId" in body
        assert "editingUsageId" in body and "editingObservationId" in body

    def test_restore_reopens_correction_mode(self):
        app = (PWA / "app.js").read_text()
        body = app.split("async function restoreDraft", 1)[1].split("\n// ----------------", 1)[0]
        assert "openLogSheet(d.editingId || null)" in body
        assert "openObservationSheet(d.editingId || null)" in body
        assert "switchProfile(owner.id)" in body           # cross-profile drafts
        assert "unfinished correction was restored" in body

    def test_draft_removed_only_after_fields_applied(self):
        app = (PWA / "app.js").read_text()
        body = app.split("async function restoreDraft", 1)[1].split("\n// ----------------", 1)[0]
        restore_tail = body.rsplit("removeItem(\"pwa-draft\")", 1)[1]
        assert "consumed only once its fields were applied" in body
        assert "toast(" in restore_tail or "removeItem" not in restore_tail

    def test_storage_failure_is_honest(self):
        app = (PWA / "app.js").read_text()
        body = app.split("function captureDraftForUpdate", 1)[1].split("\n}", 1)[0]
        assert "storeDraft(d)" in body
        assert "WILL BE LOST" in body                      # no promised restore


class TestRollbackClaimAccuracy:
    def test_store_falls_back_on_versionerror(self):
        store = (PWA / "store.js").read_text()
        assert "openDBVersioned" in store
        assert 'err.name === "VersionError"' in store
        assert "openDBVersioned(undefined)" in store

    def test_docs_no_longer_claim_revert_is_safe(self):
        for doc in ("docs/PWA.md", "docs/RECONCILIATION.md"):
            text = (ROOT / doc).read_text()
            assert "VersionError" in text
            assert "older code ignores the extra" not in text
            assert "plain code revert" in text or "plain\n  code revert" in text


class TestPolicyDraftAccuracy:
    def test_privacy_mentions_session_storage(self):
        text = (PWA / "privacy.html").read_text()
        assert "sessionStorage" in text
        assert "every profile stored on this device" in text
        assert "scoped to your own records" not in text

    def test_terms_mentions_session_storage_and_all_profiles(self):
        text = (PWA / "terms.html").read_text()
        assert "sessionStorage" in text
        assert "every profile on this device" in text

    def test_in_app_storage_note_matches(self):
        html = (PWA / "index.html").read_text()
        assert "sessionStorage" in html
        assert "every profile on this device" in html


# ---------------- training context + draft-loss fix (release pass) ----------------

class TestTrainingContextWiring:
    def test_markup_has_all_fields_collapsed_private_note(self):
        html = (PWA / "index.html").read_text()
        assert 'id="training-context"' in html
        assert "<details" in html.split('id="training-context"')[0][-200:]
        for key in ("tc_session_type", "tc_muscles", "tc_effort",
                    "tc_soreness", "tc_note"):
            assert f'data-gkey="{key}"' in html
        assert "private" in html.split('data-gkey="tc_note"')[0].split("Training context")[-1].lower() or \
               "Stays out of appointment summaries" in html

    def test_collect_goal_data_captures_training_fields(self):
        app = (PWA / "app.js").read_text()
        body = app.split("function collectGoalData", 1)[1].split("return Object.keys", 1)[0]
        assert "#observation-fields .gf" in body
        assert "#training-fields .gf" in body

    def test_sheet_collapses_training_context_on_open(self):
        app = (PWA / "app.js").read_text()
        body = app.split("function openObservationSheet", 1)[1].split("function goalFieldInput", 1)[0]
        assert '"#training-context"' in body
        assert ".open = false" in body

    def test_summary_labels_and_private_note_exclusion(self):
        app = (PWA / "app.js").read_text()
        body = app.split("const obsLines = d.observations.map", 1)[1].split("});", 1)[0]
        assert 'k !== "tc_note" || d.includeNotes' in body
        assert "TC_LABELS[k] || k" in body

    def test_history_uses_labels(self):
        app = (PWA / "app.js").read_text()
        assert "TC_LABELS[k] || k" in app.split("<span class=\"text-xs font-bold text-sky-400 uppercase\">Observation</span>", 1)[1][:400]

    def test_labels_are_neutral_no_claims(self):
        app = (PWA / "app.js").read_text()
        block = app.split("const TC_LABELS", 1)[1].split("};", 1)[0]
        assert "tc_note" in block
        for banned in ("treat", "cure", "improve", "boost", "enhance"):
            assert banned not in block.lower()

    def test_draft_picks_up_training_fields_automatically(self):
        app = (PWA / "app.js").read_text()
        body = app.split('draft.sheet = "observation"', 1)[1].split("collectDraft", 1)[0]
        assert "collectGoalData()" in body

    def test_draft_restore_covers_training_fields(self):
        app = (PWA / "app.js").read_text()
        body = app.split("async function restoreDraft", 1)[1].split("};", 1)[0]
        # restore must query the whole sheet, not only #observation-fields —
        # training-context fields live in #training-fields
        assert '#observation-sheet .gf[data-gkey=' in body
        seg = body.split('d.sheet === "observation"', 1)[1]
        assert "observation-fields .gf" not in seg


class TestDraftLossFixControllerchange:
    def test_save_draft_silently_returns_result(self):
        app = (PWA / "app.js").read_text()
        body = app.split("function saveDraftSilently", 1)[1].split("\nfunction ", 1)[0]
        assert "return storeDraft(d);" in body
        assert "return true;" in body          # nothing-to-lose path

    def test_no_auto_reload_on_storage_failure(self):
        app = (PWA / "app.js").read_text()
        seg = app.split('addEventListener("controllerchange"', 1)[1].split("});", 1)[0]
        # reload only inside the success branch or after explicit confirm
        assert "if (saveDraftSilently())" in seg
        assert seg.index("if (saveDraftSilently())") < seg.index("confirm(")
        assert "WILL BE LOST" in seg           # explicit loss warning
        assert "keeps working" in seg          # explicit recovery choice

    def test_failure_confirm_offers_update_next_reload(self):
        app = (PWA / "app.js").read_text()
        seg = app.split('addEventListener("controllerchange"', 1)[1].split("});", 1)[0]
        assert "the update will apply the next time" in seg

    def test_single_tab_confirm_behavior_unchanged(self):
        app = (PWA / "app.js").read_text()
        body = app.split("function captureDraftForUpdate", 1)[1].split("\nfunction ", 1)[0]
        assert "return confirm(" in body       # still a confirm, not forced


# ---------------- policy finalization (approved structure, 2026-11-15) ----------------

class TestPolicyFinalization:
    def test_no_medical_device_legal_assertion(self):
        text = (PWA / "terms.html").read_text()
        assert "not a medical device" not in text.lower()
        assert "does not diagnose" in text and "medical advice" in text

    def test_liability_does_not_imply_terms_eliminate_it(self):
        text = (PWA / "terms.html").read_text()
        assert "cannot be limited or excluded" in text
        assert "To the maximum extent permitted by law, the operator is not liable" not in text

    def test_open_legal_questions_surfaced(self):
        text = (PWA / "terms.html").read_text()
        assert "Open legal questions" in text
        assert "not legal clearance" in text

    def test_approved_feedback_route(self):
        for f in ("privacy.html", "index.html"):
            text = (PWA / f).read_text()
            assert "github.com/kinitiyaan-commits/peptide-safety-tracker/issues" in text
        privacy = (PWA / "privacy.html").read_text()
        assert "Issues are public" in privacy

    def test_pending_literal_values_clearly_marked(self):
        privacy = (PWA / "privacy.html").read_text()
        terms = (PWA / "terms.html").read_text()
        assert "[OWNER TO SUPPLY" in privacy   # handle + security email pending
        assert "[OWNER TO SUPPLY" in terms
        # no stale generic placeholder left
        for f in ("privacy.html", "terms.html"):
            assert "[OWNER TO CONFIRM]" not in (PWA / f).read_text()

    def test_exports_downloaded_shared_files_disclosure(self):
        text = (PWA / "privacy.html").read_text()
        assert "no longer controls it" in text
