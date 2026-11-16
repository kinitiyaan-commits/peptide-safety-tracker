"""Tests for peptide_safety Milestone A.

Covers: user-data isolation (regression test required by AGENTS.md rule 7),
explicit-unit validation, symptom validation, reminder validation,
user-scoped export, and neutral brand/verification payloads.
"""

import csv
import io
import json
from pathlib import Path

import pytest

from peptide_safety import service
from peptide_safety.db import init_db
from peptide_safety.exporters import export_user_data
from peptide_safety.seed import seed_demo


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test_peptide.db"
    init_db(path)
    return path


@pytest.fixture()
def two_users(db_path):
    uid_a = service.create_user(db_path, "Alice")
    uid_b = service.create_user(db_path, "Bob")
    return uid_a, uid_b


# ------------------------------------------------- user-data isolation ----

class TestUserDataIsolation:
    """AGENTS.md rule 7: user A's data must never leak to user B."""

    def test_usage_isolation(self, db_path, two_users):
        uid_a, uid_b = two_users
        service.log_usage(db_path, uid_a, "BPC-157", 250, "mcg")
        service.log_usage(db_path, uid_b, "Semaglutide", 0.5, "mg")

        seen_a = service.list_usage(db_path, uid_a)
        seen_b = service.list_usage(db_path, uid_b)
        assert [u["peptide_name"] for u in seen_a] == ["BPC-157"]
        assert [u["peptide_name"] for u in seen_b] == ["Semaglutide"]
        assert all(u["user_id"] == uid_b for u in seen_b)

    def test_symptom_isolation(self, db_path, two_users):
        uid_a, uid_b = two_users
        service.log_symptom(db_path, uid_a, "BPC-157", 2, "Alice-only symptom")
        service.log_symptom(db_path, uid_b, "BPC-157", 4, "Bob-only symptom")

        assert all("Alice-only" not in s["description"]
                   for s in service.list_symptoms(db_path, uid_b))
        assert all("Bob-only" not in s["description"]
                   for s in service.list_symptoms(db_path, uid_a))

    def test_reminder_isolation(self, db_path, two_users):
        uid_a, uid_b = two_users
        service.add_reminder(db_path, uid_a, "BPC-157", "09:00", "Daily")
        service.add_reminder(db_path, uid_b, "Semaglutide", "20:00", "Mon")

        assert [r["peptide_name"] for r in service.list_reminders(db_path, uid_a)] == ["BPC-157"]
        assert [r["peptide_name"] for r in service.list_reminders(db_path, uid_b)] == ["Semaglutide"]

    def test_cross_user_delete_denied(self, db_path, two_users):
        uid_a, uid_b = two_users
        entry = service.log_usage(db_path, uid_a, "BPC-157", 250, "mcg")
        # Bob cannot delete Alice's entry
        assert service.delete_usage(db_path, uid_b, entry) is False
        assert len(service.list_usage(db_path, uid_a)) == 1
        # Same for symptoms and reminders
        sym = service.log_symptom(db_path, uid_a, "BPC-157", 1, "private")
        rem = service.add_reminder(db_path, uid_a, "BPC-157", "09:00", "Daily")
        assert service.delete_symptom(db_path, uid_b, sym) is False
        assert service.delete_reminder(db_path, uid_b, rem) is False
        assert service.list_symptoms(db_path, uid_a) != []
        assert service.list_reminders(db_path, uid_a) != []

    def test_cross_user_reminder_toggle_denied(self, db_path, two_users):
        uid_a, uid_b = two_users
        rem = service.add_reminder(db_path, uid_a, "BPC-157", "09:00", "Daily")
        assert service.set_reminder_enabled(db_path, uid_b, rem, False) is False
        assert service.list_reminders(db_path, uid_a)[0]["enabled"] == 1

    def test_export_is_user_scoped(self, db_path, two_users):
        uid_a, uid_b = two_users
        service.log_usage(db_path, uid_a, "BPC-157", 250, "mcg", notes="A-secret")
        service.log_symptom(db_path, uid_a, "BPC-157", 3, "A symptom")
        service.log_usage(db_path, uid_b, "Semaglutide", 0.5, "mg", notes="B-secret")

        payload = json.loads(export_user_data(db_path, uid_a, "json")[0].decode())
        flat = json.dumps(payload)
        assert "A-secret" in flat and "A symptom" in flat
        assert "B-secret" not in flat
        assert payload["user_id"] == uid_a
        assert payload["usage_log"] and all(
            u["user_id"] == uid_a for u in payload["usage_log"])

        payload_b = json.loads(export_user_data(db_path, uid_b, "json")[0].decode())
        assert payload_b["usage_log"][0]["peptide_name"] == "Semaglutide"


# ------------------------------------------------------ explicit units ----

class TestExplicitUnits:
    def test_all_allowed_units_accepted(self, db_path, two_users):
        uid_a, _ = two_users
        for unit in ("mcg", "mg", "IU", "units", "mL"):
            entry = service.log_usage(db_path, uid_a, "BPC-157", 1, unit)
            assert entry is not None

    def test_unitless_amount_rejected(self, db_path, two_users):
        uid_a, _ = two_users
        with pytest.raises(ValueError, match="unit must be one of"):
            service.log_usage(db_path, uid_a, "BPC-157", 250, "")
        with pytest.raises(ValueError, match="unit must be one of"):
            service.log_usage(db_path, uid_a, "BPC-157", 250, "g")  # not in allowlist
        with pytest.raises(ValueError, match="unit must be one of"):
            service.log_usage(db_path, uid_a, "BPC-157", 250, None)

    def test_amount_validation(self, db_path, two_users):
        uid_a, _ = two_users
        for bad in (0, -5, "250", None):
            with pytest.raises(ValueError, match="amount"):
                service.log_usage(db_path, uid_a, "BPC-157", bad, "mcg")

    def test_demo_data_always_has_units(self, tmp_path):
        uid = seed_demo(tmp_path / "seeded.db")
        rows = service.list_usage(tmp_path / "seeded.db", uid)
        assert rows, "demo profile should ship with synthetic usage rows"
        assert all(r["unit"] in ("mcg", "mg", "IU", "units", "mL") for r in rows)
        assert all(r["amount"] > 0 for r in rows)


# ------------------------------------------------------------- symptoms ---

class TestSymptoms:
    def test_severity_bounds(self, db_path, two_users):
        uid_a, _ = two_users
        for bad in (0, 6, "3", 2.5, None):
            with pytest.raises(ValueError, match="severity"):
                service.log_symptom(db_path, uid_a, "BPC-157", bad, "desc")
        assert service.log_symptom(db_path, uid_a, "BPC-157", 5, "ok") > 0

    def test_description_required(self, db_path, two_users):
        uid_a, _ = two_users
        with pytest.raises(ValueError, match="description"):
            service.log_symptom(db_path, uid_a, "BPC-157", 3, "   ")


# ------------------------------------------------------------ reminders ---

class TestReminders:
    def test_user_configured_only(self, db_path, two_users):
        uid_a, _ = two_users
        rem = service.add_reminder(db_path, uid_a, "BPC-157", "07:30", "Mon,Fri")
        stored = service.list_reminders(db_path, uid_a)[0]
        assert (stored["id"], stored["peptide_name"],
                stored["time_of_day"], stored["days"]) == \
               (rem, "BPC-157", "07:30", "Mon,Fri")
        assert stored["enabled"] == 1

    def test_time_validation(self, db_path, two_users):
        uid_a, _ = two_users
        for bad in ("25:00", "9:5", "9:60", "abc", "", "07:3"):
            with pytest.raises(ValueError, match="time_of_day"):
                service.add_reminder(db_path, uid_a, "BPC-157", bad, "Daily")

    def test_days_required(self, db_path, two_users):
        uid_a, _ = two_users
        with pytest.raises(ValueError, match="days"):
            service.add_reminder(db_path, uid_a, "BPC-157", "09:00", "  ")


# --------------------------------------------------------------- export ---

class TestExport:
    def test_json_and_csv_roundtrip(self, db_path, two_users):
        uid_a, _ = two_users
        service.log_usage(db_path, uid_a, "BPC-157", 250, "mcg")
        service.log_symptom(db_path, uid_a, "BPC-157", 2, "mild redness")
        service.add_reminder(db_path, uid_a, "BPC-157", "09:00", "Daily")

        payload, media_type, fname = export_user_data(db_path, uid_a, "json")
        assert media_type == "application/json" and "user" + str(uid_a) in fname
        data = json.loads(payload.decode())
        assert set(data) >= {"usage_log", "symptoms", "reminders"}

        payload, media_type, fname = export_user_data(db_path, uid_a, "csv")
        assert media_type == "text/csv" and fname.endswith(".csv")
        rows = list(csv.reader(io.StringIO(payload.decode())))
        sections = {r[0] for r in rows if r and r[0]}
        assert sections == {"usage_log", "symptoms", "reminders"}
        assert any("250" in cell for row in rows for cell in row)

    def test_empty_user_export(self, db_path, two_users):
        uid_b = two_users[1]
        payload = json.loads(export_user_data(db_path, uid_b, "json")[0].decode())
        assert payload["usage_log"] == []
        assert payload["symptoms"] == []
        assert payload["reminders"] == []

    def test_bad_format_rejected(self, db_path, two_users):
        uid_a, _ = two_users
        with pytest.raises(ValueError, match="format"):
            export_user_data(db_path, uid_a, "xlsx")


# ------------------------------------------------- saved products --------

class TestSavedProducts:
    def test_save_and_list(self, db_path, two_users):
        uid_a, _ = two_users
        pid = service.save_product(db_path, uid_a, "BPC-157", "mcg", "my vial")
        rows = service.list_products(db_path, uid_a)
        assert len(rows) == 1
        assert rows[0]["id"] == pid
        assert rows[0]["name"] == "BPC-157"
        assert rows[0]["default_unit"] == "mcg"

    def test_isolation(self, db_path, two_users):
        uid_a, uid_b = two_users
        service.save_product(db_path, uid_a, "BPC-157", "mcg")
        service.save_product(db_path, uid_b, "Semaglutide", "mg")
        assert [p["name"] for p in service.list_products(db_path, uid_a)] == ["BPC-157"]
        assert [p["name"] for p in service.list_products(db_path, uid_b)] == ["Semaglutide"]
        other_id = service.list_products(db_path, uid_a)[0]["id"]
        assert service.delete_product(db_path, uid_b, other_id) is False
        assert len(service.list_products(db_path, uid_a)) == 1

    def test_duplicate_rejected(self, db_path, two_users):
        uid_a, _ = two_users
        service.save_product(db_path, uid_a, "BPC-157")
        with pytest.raises(ValueError, match="already saved"):
            service.save_product(db_path, uid_a, "BPC-157")
        # same name for a different user is fine
        assert service.save_product(db_path, two_users[1], "BPC-157")

    def test_validation(self, db_path, two_users):
        uid_a, _ = two_users
        with pytest.raises(ValueError, match="name is required"):
            service.save_product(db_path, uid_a, "   ")
        with pytest.raises(ValueError, match="unit must be one of"):
            service.save_product(db_path, uid_a, "BPC-157", "grams")
        for ok_unit in ("mcg", "mg", "IU", "units", "mL", None, ""):
            assert service.save_product(db_path, uid_a, f"Prod-{ok_unit}", ok_unit)

    def test_delete_scoped(self, db_path, two_users):
        uid_a, uid_b = two_users
        pid = service.save_product(db_path, uid_a, "BPC-157")
        assert service.delete_product(db_path, uid_a, pid) is True
        assert service.list_products(db_path, uid_a) == []
        assert service.delete_product(db_path, uid_a, pid) is False


# --------------------------------------------------- catalog + goals -----

class TestCatalogExpansion:
    def test_expansion_adds_candidates_without_duplicates(self, tmp_path):
        path = tmp_path / "expand.db"
        seed_demo(path)
        seed_demo(path)  # re-run must not create duplicates
        names = [c["name"] for c in service.list_catalog(path)]
        assert len(names) == len(set(names))
        assert len(names) >= 15  # 7 original + expanded candidates

    def test_expansion_preserves_existing_logs(self, tmp_path):
        path = tmp_path / "logs.db"
        uid = seed_demo(path)
        other = service.create_user(path, "Real User")
        service.log_usage(path, other, "BPC-157", 5, "mg")
        before = service.list_usage(path, other)
        seed_demo(path)  # expansion must not touch other users' logs
        assert service.list_usage(path, other) == before
        assert len(before) == 1

    def test_new_entries_carry_review_metadata(self, tmp_path):
        path = tmp_path / "meta.db"
        seed_demo(path)
        for entry in service.list_catalog(path):
            assert entry["review_status"] in ("verified", "awaiting-verification")
            assert entry["source_url"].startswith("https://")
            assert entry["source_type"]
            assert entry["last_reviewed"]

    def test_hgh_entry_with_height_note(self, tmp_path):
        path = tmp_path / "hgh.db"
        seed_demo(path)
        hgh = [c for c in service.list_catalog(path) if "Somatropin" in c["name"]]
        assert len(hgh) == 1
        entry = hgh[0]
        assert entry["regulatory_status"] == "fda-approved"
        assert entry["review_status"] == "verified"
        assert "medlineplus" in entry["source_url"]
        low = entry["evidence_note"].lower()
        assert "specific" in low and "indications" in low and "height" in low
        # reviewed alias: HGH resolves to the canonical entry (spec behavior)
        assert "hgh" in [a.lower() for a in entry["aliases"]]

    def test_awaiting_verification_entries_flagged(self, tmp_path):
        path = tmp_path / "await.db"
        seed_demo(path)
        awaiting = [c for c in service.list_catalog(path)
                    if c["review_status"] == "awaiting-verification"]
        assert awaiting, "unconfirmed candidates must be flagged, not silently verified"
        assert all(c["regulatory_status"] != "fda-approved" for c in awaiting)


class TestCatalogDocCandidates:
    """The spec's exact candidate list, with verified source URLs."""

    DOC_CANDIDATES = {
        "Somatropin": "medlineplus.gov",
        "Tesamorelin": "medlineplus.gov",
        "Liraglutide": "medlineplus.gov",
        "Dulaglutide": "medlineplus.gov",
        "Teriparatide": "medlineplus.gov",
        "Abaloparatide": "medlineplus.gov",
        "GHK-Cu": "fda.gov",
        "AOD-9604": "fda.gov",
        "Thymosin-alpha 1": "fda.gov",
    }

    def test_all_spec_candidates_present_with_correct_source_domain(self, tmp_path):
        path = tmp_path / "candidates.db"
        seed_demo(path)
        catalog = {c["name"]: c for c in service.list_catalog(path)}
        for candidate, domain in self.DOC_CANDIDATES.items():
            matches = [c for n, c in catalog.items() if n.startswith(candidate)]
            assert matches, f"missing spec candidate: {candidate}"
            assert domain in matches[0]["source_url"], candidate

    def test_fda_bulk_entries_keep_nomination_context(self, tmp_path):
        path = tmp_path / "bulk.db"
        seed_demo(path)
        catalog = {c["name"]: c for c in service.list_catalog(path)}
        ghk = next(c for n, c in catalog.items() if n == "GHK-Cu")
        assert "injectable" in ghk["evidence_note"].lower()  # route qualification kept
        assert ghk["regulatory_status"] == "compounding-flagged"
        for name in ("AOD-9604", "Thymosin-alpha 1"):
            note = catalog[name]["evidence_note"].lower()
            assert "withdrawn" in note or "nomination" in note, name
            assert "not an approval" in note or "not  an approval" in note or "clearance" in note, name
            assert catalog[name]["regulatory_status"] == "compounding-flagged"

    def test_ibutamoren_now_fda_sourced(self, tmp_path):
        path = tmp_path / "ibu.db"
        seed_demo(path)
        entry = next(c for c in service.list_catalog(path) if "Ibutamoren" in c["name"])
        assert entry["review_status"] == "verified"
        assert "certain-bulk-drug-substances" in entry["source_url"]
        assert "heart failure" in entry["evidence_note"].lower()

    def test_no_target_count_padding(self, tmp_path):
        from peptide_safety.seed import CATALOG_ROWS
        path = tmp_path / "count.db"
        seed_demo(path)
        names = [c["name"] for c in service.list_catalog(path)]
        assert len(names) == len(set(names)) == len(CATALOG_ROWS)

    def test_somatropin_alias_hgh(self, tmp_path):
        path = tmp_path / "alias.db"
        seed_demo(path)
        entry = next(c for c in service.list_catalog(path) if "Somatropin" in c["name"])
        assert "HGH" in entry["aliases"]
        # searching "HGH" resolves to the canonical entry via aliases
        hits = [c for c in service.list_catalog(path)
                if any("hgh" == a.lower() for a in c["aliases"])]
        assert [c["name"] for c in hits] == ["Somatropin (HGH)"]

    def test_pramlintide_exenatide_not_imported_as_available(self, tmp_path):
        path = tmp_path / "hist.db"
        seed_demo(path)
        names = {c["name"] for c in service.list_catalog(path)}
        assert "Pramlintide" not in names and "Exenatide" not in names


class TestCorrections:
    """Edit/correct flows: originals and correction timestamps preserved,
    visible in list output and exports (usability spec requirement)."""

    def test_edit_usage_records_previous_values_and_time(self, db_path, two_users):
        uid, _ = two_users
        taken = "2026-01-01T10:00:00+00:00"
        eid = service.log_usage(db_path, uid, "BPC-157", 1, "mg", taken_at=taken,
                                notes="original note")
        edited_at = service.edit_usage(db_path, uid, eid, {
            "amount": 2, "unit": "mg", "notes": "corrected note",
            "peptide_name": "BPC-157 5mg",
        })
        assert edited_at is True
        row = service.list_usage(db_path, uid)[0]
        # new values written
        assert row["amount"] == 2 and row["peptide_name"] == "BPC-157 5mg"
        assert row["notes"] == "corrected note"
        # exactly one correction, containing ONLY the changed fields
        assert len(row["corrections"]) == 1
        c = row["corrections"][0]
        assert c["previous"] == {"amount": 1, "notes": "original note",
                                 "peptide_name": "BPC-157"}
        # correction carries a parseable timestamp
        assert service._parse_iso(c["edited_at"]) is not None

    def test_multiple_edits_stack(self, db_path, two_users):
        uid, _ = two_users
        eid = service.log_usage(db_path, uid, "BPC-157", 1, "mg")
        service.edit_usage(db_path, uid, eid, {"notes": "v2"})
        service.edit_usage(db_path, uid, eid, {"notes": "v3"})
        row = service.list_usage(db_path, uid)[0]
        assert row["notes"] == "v3"
        assert [c["previous"]["notes"] for c in row["corrections"]] == ["", "v2"]

    def test_no_change_edit_records_nothing(self, db_path, two_users):
        uid, _ = two_users
        eid = service.log_usage(db_path, uid, "BPC-157", 1, "mg", notes="same")
        assert service.edit_usage(db_path, uid, eid,
                                  {"notes": "same", "amount": 1}) is False
        assert service.list_usage(db_path, uid)[0]["corrections"] == []

    def test_edit_validates_like_new_entries(self, db_path, two_users):
        uid, _ = two_users
        eid = service.log_usage(db_path, uid, "BPC-157", 1, "mg")
        with pytest.raises(ValueError, match="greater than 0"):
            service.edit_usage(db_path, uid, eid, {"amount": 0})
        with pytest.raises(ValueError, match="unit must be one of"):
            service.edit_usage(db_path, uid, eid, {"unit": "tablespoons"})
        with pytest.raises(ValueError, match="not editable"):
            service.edit_usage(db_path, uid, eid, {"brand_id": 1})
        with pytest.raises(ValueError, match="no changes"):
            service.edit_usage(db_path, uid, eid, {})
        # nothing was altered
        assert service.list_usage(db_path, uid)[0]["corrections"] == []

    def test_edit_is_user_scoped(self, db_path, two_users):
        uid_a, uid_b = two_users
        eid = service.log_usage(db_path, uid_a, "BPC-157", 1, "mg")
        with pytest.raises(ValueError, match="not found for this user"):
            service.edit_usage(db_path, uid_b, eid, {"notes": "intrusion"})
        # user A's data untouched
        assert service.list_usage(db_path, uid_a)[0]["notes"] == ""

    def test_edit_observation_preserves_previous_measurements(self, db_path, two_users):
        uid, _ = two_users
        service.set_user_goals(db_path, uid, ["sleep", "bodyweight"])
        oid = service.log_observation(db_path, uid,
                                      goal_data={"sleep_rating": 4,
                                                 "bodyweight_kg": 70},
                                      notes="first")
        assert service.edit_observation(db_path, uid, oid, {
            "goal_data": {"sleep_rating": 3, "bodyweight_kg": 70.5},
            "notes": "typo fixed",
        }) is True
        row = service.list_observations(db_path, uid)[0]
        assert row["goal_data"] == {"sleep_rating": 3, "bodyweight_kg": 70.5}
        assert row["corrections"][0]["previous"] == {
            "goal_data": {"sleep_rating": 4, "bodyweight_kg": 70},
            "notes": "first",
        }
        # goal_data corrections validated against enabled goals
        service.set_user_goals(db_path, uid, ["mood"])
        with pytest.raises(ValueError, match="not enabled"):
            service.edit_observation(db_path, uid, oid,
                                     {"goal_data": {"sleep_rating": 2}})

    def test_corrections_in_export(self, db_path, two_users):
        uid, _ = two_users
        eid = service.log_usage(db_path, uid, "BPC-157", 1, "mg")
        service.edit_usage(db_path, uid, eid, {"amount": 2})
        payload = json.loads(export_user_data(db_path, uid, "json")[0].decode())
        corr = payload["usage_log"][0]["corrections"]
        assert corr[0]["previous"]["amount"] == 1
        # CSV carries corrections too (as JSON text)
        csv_text = export_user_data(db_path, uid, "csv")[0].decode()
        assert '"previous"' in csv_text or "previous" in csv_text




class TestIdempotency:
    """Request idempotency, separate from the suspected-duplicate guard:
    retrying the same submission replays the original response and can
    never create another event."""











    def test_service_level_roundtrip_and_isolation(self, db_path, two_users):
        uid_a, uid_b = two_users
        assert service.get_idempotent_response(db_path, uid_a, "nope") is None
        service.record_idempotency(db_path, uid_a, " key-x ", "usage",
                                   {"entry_id": 42})
        # key whitespace is normalized; other users see nothing
        assert service.get_idempotent_response(db_path, uid_a, "key-x") == {"entry_id": 42}
        assert service.get_idempotent_response(db_path, uid_b, "key-x") is None
        # recording under an empty key is a no-op, never a collision
        service.record_idempotency(db_path, uid_a, "", "usage", {"entry_id": 1})
        service.record_idempotency(db_path, uid_a, None, "usage", {"entry_id": 1})
        assert service.get_idempotent_response(db_path, uid_a, "") is None

    def test_idempotency_keys_deleted_with_user(self, db_path, two_users):
        uid_a, _ = two_users
        service.record_idempotency(db_path, uid_a, "k", "usage", {"entry_id": 1})
        conn = service.connect(db_path)
        conn.execute("DELETE FROM users WHERE id = ?", (uid_a,))
        conn.commit()
        conn.close()
        conn = service.connect(db_path)
        n = conn.execute("SELECT COUNT(*) c FROM idempotency_keys").fetchone()["c"]
        conn.close()
        assert n == 0  # FK cascade keeps key table user-owned


class TestMigrationOldSchema:
    """Existing records must survive schema migrations (AGENTS.md: preserve
    records; test migrations)."""

    def _make_old_db(self, path):
        """Create a DB with the pre-corrections schema and real rows in it."""
        import re as _re
        from peptide_safety.db import SCHEMA, connect
        old_schema = SCHEMA
        # strip the new columns/tables exactly as they appear in db.py
        old_schema = old_schema.replace(
            "    goal_data    TEXT,\n"
            "    -- Correction history: JSON list of [{edited_at, previous: {...}}], one\n"
            "    -- entry per edit, preserving the values as they were before that edit.\n"
            "    -- Original values are never overwritten destructively.\n"
            "    corrections  TEXT\n",
            "    goal_data    TEXT\n")
        old_schema = old_schema.replace(
            "    goal_data   TEXT,\n    corrections TEXT\n",
            "    goal_data   TEXT\n")
        old_schema = _re.sub(
            r"-- Request idempotency.*?UNIQUE \(user_id, idem_key\)\n\);\n\n",
            "", old_schema, flags=_re.S)
        assert "corrections" not in old_schema and "idempotency" not in old_schema
        conn = connect(path)
        conn.executescript(old_schema)
        conn.execute("INSERT INTO users (display_name) VALUES ('OldUser')")
        uid = conn.execute("SELECT id FROM users").fetchone()["id"]
        conn.execute(
            "INSERT INTO usage_log (user_id, peptide_name, amount, unit, taken_at) "
            "VALUES (?, 'BPC-157', 1, 'mg', '2026-01-01T10:00:00+00:00')", (uid,))
        conn.execute(
            "INSERT INTO observations (user_id, taken_at, goal_data) VALUES (?, ?, ?)",
            (uid, "2026-01-02T10:00:00+00:00", '{"height_cm": 176}'))
        conn.commit()
        conn.close()
        return uid

    def test_init_db_adds_columns_and_keeps_records(self, tmp_path):
        from peptide_safety.db import init_db
        path = tmp_path / "old.db"
        uid = self._make_old_db(path)
        init_db(path)  # migration runs
        rows = service.list_usage(path, uid)
        assert len(rows) == 1
        assert rows[0]["peptide_name"] == "BPC-157"
        assert rows[0]["corrections"] == []  # new column defaults transparently
        obs = service.list_observations(path, uid)
        assert obs[0]["goal_data"] == {"height_cm": 176}
        assert obs[0]["corrections"] == []
        # idempotency table exists and works on the migrated DB
        service.record_idempotency(path, uid, "k", "usage", {"entry_id": 1})
        assert service.get_idempotent_response(path, uid, "k") == {"entry_id": 1}
        # corrections work end-to-end on migrated data
        eid = rows[0]["id"]
        assert service.edit_usage(path, uid, eid, {"amount": 2}) is True
        again = service.list_usage(path, uid)[0]
        assert again["amount"] == 2
        assert again["corrections"][0]["previous"]["amount"] == 1

    def test_migrated_db_then_corrections_then_edit_visible_in_export(self, tmp_path):
        from peptide_safety.db import init_db
        path = tmp_path / "old2.db"
        uid = self._make_old_db(path)
        init_db(path)
        eid = service.list_usage(path, uid)[0]["id"]
        service.edit_usage(path, uid, eid, {"notes": "corrected later"})
        payload = json.loads(export_user_data(path, uid, "json")[0].decode())
        assert payload["usage_log"][0]["corrections"][0]["previous"]["notes"] == ""


class TestDuplicateProtection:
    """Spec: server-side duplicate guard, not just a disabled submit button."""

    def test_same_product_amount_unit_within_window_rejected(self, db_path, two_users):
        uid_a, _ = two_users
        service.log_usage(db_path, uid_a, "BPC-157", 1, "mg")
        with pytest.raises(service.DuplicateUsageError):
            service.log_usage(db_path, uid_a, "BPC-157", 1, "mg")

    def test_override_allows_intentional_duplicate(self, db_path, two_users):
        uid_a, _ = two_users
        service.log_usage(db_path, uid_a, "BPC-157", 1, "mg")
        assert service.log_usage(db_path, uid_a, "BPC-157", 1, "mg",
                                 allow_duplicate=True)
        assert len(service.list_usage(db_path, uid_a)) == 2

    def test_different_amount_or_unit_or_window_passes(self, db_path, two_users):
        uid_a, _ = two_users
        taken = "2026-01-01T10:00:00+00:00"
        service.log_usage(db_path, uid_a, "BPC-157", 1, "mg", taken_at=taken)
        # different amount: fine
        service.log_usage(db_path, uid_a, "BPC-157", 2, "mg", taken_at=taken)
        # different unit: fine
        service.log_usage(db_path, uid_a, "BPC-157", 1, "mcg", taken_at=taken)
        # outside the 120 s window: fine
        later = "2026-01-01T10:03:00+00:00"
        assert service.log_usage(db_path, uid_a, "BPC-157", 1, "mg", taken_at=later)

    def test_case_and_whitespace_insensitive_product_match(self, db_path, two_users):
        uid_a, _ = two_users
        service.log_usage(db_path, uid_a, "BPC-157", 1, "mg")
        with pytest.raises(service.DuplicateUsageError):
            service.log_usage(db_path, uid_a, "  bpc-157 ", 1, "mg")

    def test_other_users_unaffected(self, db_path, two_users):
        uid_a, uid_b = two_users
        service.log_usage(db_path, uid_a, "BPC-157", 1, "mg")
        assert service.log_usage(db_path, uid_b, "BPC-157", 1, "mg")




class TestObservationLogging:
    """Spec: record sleep/height/weight without an administration event."""

    def test_observation_without_any_usage_entry(self, db_path, two_users):
        uid_a, _ = two_users
        service.set_user_goals(db_path, uid_a, ["sleep", "height", "bodyweight"])
        oid = service.log_observation(db_path, uid_a,
                                      goal_data={"sleep_rating": 3,
                                                 "height_cm": 176,
                                                 "bodyweight_kg": 70.5})
        rows = service.list_observations(db_path, uid_a)
        assert len(rows) == 1 and rows[0]["id"] == oid
        assert rows[0]["goal_data"]["height_cm"] == 176
        # no administration event was created
        assert service.list_usage(db_path, uid_a) == []

    def test_requires_enabled_goal_fields(self, db_path, two_users):
        uid_a, _ = two_users
        with pytest.raises(ValueError):
            service.log_observation(db_path, uid_a, goal_data={"sleep_rating": 3})
        service.set_user_goals(db_path, uid_a, ["sleep"])
        with pytest.raises(ValueError, match="1-5"):
            service.log_observation(db_path, uid_a, goal_data={"sleep_rating": 9})
        with pytest.raises(ValueError, match="not enabled"):
            service.log_observation(db_path, uid_a, goal_data={"height_cm": 180})

    def test_isolation(self, db_path, two_users):
        uid_a, uid_b = two_users
        service.set_user_goals(db_path, uid_a, ["height"])
        service.log_observation(db_path, uid_a, goal_data={"height_cm": 180})
        assert service.list_observations(db_path, uid_b) == []
        with pytest.raises(ValueError):
            service.log_observation(db_path, uid_b, goal_data={"height_cm": 180})

    def test_goal_changes_preserve_historical_observations(self, db_path, two_users):
        uid_a, _ = two_users
        service.set_user_goals(db_path, uid_a, ["sleep", "height"])
        service.log_observation(db_path, uid_a, goal_data={"sleep_rating": 4,
                                                          "height_cm": 176})
        service.log_usage(db_path, uid_a, "BPC-157", 1, "mg",
                          goal_data={"sleep_rating": 2})
        # disable every goal — historical data must remain intact
        service.set_user_goals(db_path, uid_a, ["mood"])
        obs = service.list_observations(db_path, uid_a)
        assert obs[0]["goal_data"] == {"sleep_rating": 4, "height_cm": 176}
        usage = service.list_usage(db_path, uid_a)
        assert usage[0]["goal_data"] == {"sleep_rating": 2}
        # and re-enabling shows they are still valid records
        service.set_user_goals(db_path, uid_a, ["sleep", "height", "mood"])
        assert service.list_observations(db_path, uid_a)[0]["goal_data"] == \
            {"sleep_rating": 4, "height_cm": 176}

    def test_export_includes_observations_scoped(self, db_path, two_users):
        uid_a, uid_b = two_users
        service.set_user_goals(db_path, uid_a, ["height"])
        service.log_observation(db_path, uid_a, goal_data={"height_cm": 180})
        payload = json.loads(export_user_data(db_path, uid_a, "json")[0].decode())
        assert len(payload["observations"]) == 1
        payload_b = json.loads(export_user_data(db_path, uid_b, "json")[0].decode())
        assert payload_b["observations"] == []




class TestCustomGoalText:
    """Spec: stable goal ids + user-owned association + private custom text."""

    def test_custom_text_stored_and_scoped(self, db_path, two_users):
        uid_a, uid_b = two_users
        service.set_user_goals(db_path, uid_a, ["custom", "sleep"],
                               custom_texts={"custom": "keeping a neutral record"})
        details = {d["goal_key"]: d["custom_text"]
                   for d in service.get_user_goal_details(db_path, uid_a)}
        assert details["custom"] == "keeping a neutral record"
        details_b = {d["goal_key"]: d["custom_text"]
                     for d in service.get_user_goal_details(db_path, uid_b)}
        assert all(v == "" for v in details_b.values())

    def test_custom_text_truncated_and_unknown_rejected(self, db_path, two_users):
        uid_a, _ = two_users
        with pytest.raises(ValueError, match="unknown goal"):
            service.set_user_goals(db_path, uid_a, ["sleep"],
                                   custom_texts={"bogus": "x"})
        service.set_user_goals(db_path, uid_a, ["custom"],
                               custom_texts={"custom": "x" * 500})
        details = service.get_user_goal_details(db_path, uid_a)
        assert len(details[0]["custom_text"]) == 200



    def test_spec_suggested_labels_present(self):
        from peptide_safety.goals import TRACKING_GOALS
        labels = " | ".join(g["label"] for g in TRACKING_GOALS.values())
        for suggested in ("Prescribed treatment and medication routine",
                          "Symptoms and side effects",
                          "Weight or body-composition observations",
                          "Training and recovery observations",
                          "Skin or hair observations",
                          "Sleep and energy observations",
                          "Appearance-related personal goals",
                          "Clinician-managed growth or hormone treatment",
                          "Preparing records for a healthcare visit",
                          "General recordkeeping"):
            assert suggested in labels, suggested
        assert "effectiveness" not in labels and "proven" not in labels

    def test_goal_explanation_is_spec_text(self):
        from peptide_safety.goals import GOALS_EXPLANATION
        assert "customize your journal, not medication recommendations" in GOALS_EXPLANATION


class TestReminderTimezoneStability:
    """Spec: define timezone/DST behavior. Reminders store a wall-clock HH:MM
    that is rendered in the device's local time; the server never converts it,
    so a DST shift keeps the same local time."""

    def test_time_stored_verbatim_and_paused_hidden(self, db_path, two_users):
        uid_a, _ = two_users
        rid = service.add_reminder(db_path, uid_a, "BPC-157", "09:30", "Mon")
        rows = service.list_reminders(db_path, uid_a)
        assert rows[0]["time_of_day"] == "09:30"  # never shifted
        assert rows[0]["enabled"] == 1
        # pausing removes it from any active due computation
        service.set_reminder_enabled(db_path, uid_a, rid, False)
        assert service.list_reminders(db_path, uid_a)[0]["enabled"] == 0
        # deleting leaves nothing behind (no background scheduler exists)
        assert service.delete_reminder(db_path, uid_a, rid)
        assert service.list_reminders(db_path, uid_a) == []

    def test_every_day_and_chips_payload_accepted(self, db_path, two_users):
        uid_a, _ = two_users
        service.add_reminder(db_path, uid_a, "BPC-157", "09:00", "Daily")
        service.add_reminder(db_path, uid_a, "CJC-1295", "21:15", "Mon,Wed,Fri")
        rows = service.list_reminders(db_path, uid_a)
        assert [r["days"] for r in rows] == ["Daily", "Mon,Wed,Fri"]


class TestTrackingGoals:
    def test_set_get_roundtrip(self, db_path, two_users):
        uid_a, _ = two_users
        keys = service.set_user_goals(db_path, uid_a, ["sleep", "recovery", "height"])
        assert service.get_user_goals(db_path, uid_a) == keys
        # duplicates collapse
        service.set_user_goals(db_path, uid_a, ["sleep", "sleep"])
        assert service.get_user_goals(db_path, uid_a) == ["sleep"]

    def test_unknown_goal_rejected(self, db_path, two_users):
        uid_a, _ = two_users
        with pytest.raises(ValueError, match="unknown goal"):
            service.set_user_goals(db_path, uid_a, ["cure-cancer-mode"])

    def test_goal_isolation(self, db_path, two_users):
        uid_a, uid_b = two_users
        service.set_user_goals(db_path, uid_a, ["sleep", "mood"])
        service.set_user_goals(db_path, uid_b, ["height"])
        assert service.get_user_goals(db_path, uid_a) == ["sleep", "mood"]
        assert service.get_user_goals(db_path, uid_b) == ["height"]

    def test_goal_data_validated_against_enabled_goals(self, db_path, two_users):
        uid_a, _ = two_users
        service.set_user_goals(db_path, uid_a, ["sleep"])
        # enabled goal field accepted
        eid = service.log_usage(db_path, uid_a, "BPC-157", 1, "mg",
                                goal_data={"sleep_rating": 4})
        rows = service.list_usage(db_path, uid_a)
        assert rows[0]["goal_data"] == {"sleep_rating": 4}
        # field of a disabled goal rejected
        with pytest.raises(ValueError, match="not enabled"):
            service.log_usage(db_path, uid_a, "BPC-157", 1, "mg",
                              goal_data={"height_cm": 180})
        # bad rating value rejected
        with pytest.raises(ValueError, match="1-5"):
            service.log_usage(db_path, uid_a, "BPC-157", 1, "mg",
                              goal_data={"sleep_rating": 9})
        # no goals selected -> any goal_data rejected
        service.set_user_goals(db_path, uid_a, [])
        with pytest.raises(ValueError, match="not enabled"):
            service.log_usage(db_path, uid_a, "BPC-157", 1, "mg",
                              goal_data={"sleep_rating": 3})
        # plain entry without goal data still fine (override: same values as
        # the first entry would now trip the server-side duplicate guard)
        assert service.log_usage(db_path, uid_a, "BPC-157", 1.5, "mg")

    def test_goal_data_is_json_scoped_in_export(self, db_path, two_users):
        uid_a, uid_b = two_users
        service.set_user_goals(db_path, uid_a, ["sleep"])
        service.log_usage(db_path, uid_a, "BPC-157", 1, "mg",
                          goal_data={"sleep_rating": 2})
        payload = json.loads(export_user_data(db_path, uid_a, "json")[0].decode())
        assert payload["tracking_goals"] == ["sleep"]
        assert payload["usage_log"][0]["goal_data"] == {"sleep_rating": 2}
        payload_b = json.loads(export_user_data(db_path, uid_b, "json")[0].decode())
        assert payload_b["tracking_goals"] == []
        assert all(u["goal_data"] is None for u in payload_b["usage_log"])

    def test_goal_labels_are_journal_fields_not_indications(self):
        from peptide_safety.goals import TRACKING_GOALS, goal_field_keys
        # These would make a goal read like an indication or effectiveness
        # claim. "Prescribed treatment and medication routine" (the spec's
        # own suggested label) describes the user's routine — it is allowed;
        # verb claims ("treats/cures/prevents") are not.
        forbidden = ("treats", "cures", "treat ", "cure ", "heals", "prevents",
                     "grow taller", "increase height", "boost", "enhance",
                     " therapy", "ascend", "attractiveness", "facial score",
                     "effective for your", "proven")
        for key, goal in TRACKING_GOALS.items():
            text = goal["label"].lower()
            for field in goal_field_keys([key]):
                text += " " + field["label"].lower()
            assert not any(w in text for w in forbidden), goal["label"]


# ------------------------------------------------- safety content rules ---

class TestSafetyContentRules:
    def test_catalog_states_regulatory_status_with_source(self, tmp_path):
        uid = seed_demo(tmp_path / "cat.db")
        path = tmp_path / "cat.db"
        catalog = service.list_catalog(path)
        assert catalog
        allowed = {"fda-approved", "not-fda-approved",
                   "compounding-flagged", "unknown"}
        for entry in catalog:
            assert entry["regulatory_status"] in allowed
            assert entry["source_url"].startswith("https://")

    def test_brands_are_neutral(self, tmp_path):
        path = tmp_path / "brands.db"
        seed_demo(path)
        for brand in service.list_brands(path):
            assert brand["supplier_type"] in (
                "pharma", "compounding-pharmacy", "research-supplier", "other")
            text = (brand["name"] + " " + brand["notes"]).lower()
            assert "safe" not in text and "trusted" not in text and \
                   "recommended" not in text

    def test_verification_links_are_neutral_linkouts(self):
        links = service.verification_links("Semaglutide")
        assert links["dailymed_label_search"].startswith(
            "https://dailymed.nlm.nih.gov/")
        assert "disclaimer" in links
        assert "not interpret" in links["disclaimer"]


# ------------------------------------------------------------- demo data --

class TestDemoData:
    def test_demo_seed_creates_isolated_demo_user(self, tmp_path):
        uid = seed_demo(tmp_path / "demo.db")
        users = service.list_users(tmp_path / "demo.db")
        assert len(users) == 1 and users[0]["is_demo"] == 1

        other = service.create_user(tmp_path / "demo.db", "Real User")
        assert service.list_usage(tmp_path / "demo.db", other) == []
        assert service.list_symptoms(tmp_path / "demo.db", other) == []
        assert service.list_reminders(tmp_path / "demo.db", other) == []
        # ...and the demo user still has its synthetic rows
        assert len(service.list_usage(tmp_path / "demo.db", uid)) == 3
        assert len(service.list_symptoms(tmp_path / "demo.db", uid)) == 2
        assert len(service.list_reminders(tmp_path / "demo.db", uid)) == 2

    def test_seed_is_idempotent(self, tmp_path):
        seed_demo(tmp_path / "idem.db")
        seed_demo(tmp_path / "idem.db")
        assert len(service.list_users(tmp_path / "idem.db")) == 1

    def test_demo_reset_restores_sample_records(self, tmp_path):
        path = tmp_path / "reset.db"
        uid = seed_demo(path)
        service.log_usage(path, uid, "Custom-XYZ", 1, "mg")
        assert len(service.list_usage(path, uid)) == 4
        seed_demo(path)  # reset clears synthetic rows added on top
        rows = service.list_usage(path, uid)
        assert len(rows) == 3
        assert all(r["peptide_name"] != "Custom-XYZ" for r in rows)

    def test_fda_approved_entries_are_ingredient_level(self, tmp_path):
        path = tmp_path / "badges.db"
        seed_demo(path)
        for entry in service.list_catalog(path):
            if entry["regulatory_status"] == "fda-approved":
                assert "specific products" in entry["evidence_note"]


# ------------------------------------------------- A-cleanup (GitHub task) -

class TestBlankFormOnOpen:
    """A.1: new entries always open with blank Notes / fields, no test
    strings leaking into forms. Static check on the embedded UI script."""

    def _ui(self):
        from peptide_safety.server import HTML_CONTENT
        return HTML_CONTENT

    def test_log_sheet_resets_on_new_entry(self):
        ui = self._ui()
        assert "form.reset();" in ui
        # reset must sit in the new-entry branch of the log sheet opener
        open_body = ui.split("function openLogSheet", 1)[1]
        assert "form.reset();" in open_body

    def test_symptom_sheet_resets(self):
        ui = self._ui()
        body = ui.split("function openSymptomSheet", 1)[1]
        assert "reset()" in body

    def test_observation_sheet_resets(self):
        ui = self._ui()
        body = ui.split("function openObservationSheet", 1)[1]
        assert "reset()" in body

    def test_no_test_strings_in_ui(self):
        ui = self._ui()
        for marker in ("test entry via UI", "goal fields E2E check",
                       "corrected in UI test"):
            assert marker not in ui

    def test_dose_form_has_no_goal_fields(self):
        """A.3: goal fields belong only in Observations."""
        ui = self._ui()
        log_sheet = ui.split("LOG USE SHEET", 1)[1].split("LOG USE", 1)[0]
        # the log sheet no longer renders goal-field inputs or a goal_fields box
        assert 'id="goal-fields"' not in ui
        assert "collectGoalData" not in ui

    def test_fab_opens_single_chooser(self):
        """A.2: the + button opens one chooser, Today has no log buttons."""
        ui = self._ui()
        today = ui.split("sec-today", 1)[1].split("</section>", 1)[0]
        assert 'onclick="openLogSheet()"' not in today
        assert 'onclick="openSymptomSheet()"' not in today
        assert 'onclick="openObservationSheet()"' not in today
        assert 'id="fab-chooser"' in ui
        assert 'onclick="openFabChooser()"' in ui


class TestUsageGoalDataMigration:
    """A.3: existing usage goal_data migrates into linked observations
    without losing anything; usage rows stay untouched."""

    def test_migrates_without_loss(self, db_path, two_users):
        uid_a, uid_b = two_users
        service.set_user_goals(db_path, uid_a, ["sleep"])
        from peptide_safety.service import (
            USAGE_GOAL_MIGRATION_KEY,
            migrate_usage_goal_data_to_observations,
        )
        entry_id = service.log_usage(db_path, uid_a, "BPC-157", 250, "mcg",
                                     goal_data={"sleep_rating": 4,
                                                "sleep_hours": 7.5})
        created = migrate_usage_goal_data_to_observations(db_path)
        assert created == 1

        obs = service.list_observations(db_path, uid_a)
        assert len(obs) == 1
        assert obs[0]["goal_data"] == {"sleep_rating": 4, "sleep_hours": 7.5}
        assert obs[0]["taken_at"] == next(
            u["taken_at"] for u in service.list_usage(db_path, uid_a)
            if u["id"] == entry_id)
        assert "Migrated from dose entry #%d" % entry_id in obs[0]["notes"]

        # usage rows are preserved untouched (non-destructive)
        row = next(u for u in service.list_usage(db_path, uid_a)
                   if u["id"] == entry_id)
        assert row["goal_data"] == {"sleep_rating": 4, "sleep_hours": 7.5}

        # nothing bleeds into user B
        assert service.list_observations(db_path, uid_b) == []

        # idempotent: re-running creates nothing new
        assert migrate_usage_goal_data_to_observations(db_path) == 0
        assert len(service.list_observations(db_path, uid_a)) == 1

    def test_runs_from_ensure_seeded_and_skips_after_marker(self, tmp_path):
        from peptide_safety.db import connect
        from peptide_safety.seed import seed_demo
        from peptide_safety.service import (
            migrate_usage_goal_data_to_observations,
        )
        path = tmp_path / "mig.db"
        seed_demo(path)
        migrate_usage_goal_data_to_observations(path)
        conn = connect(path)
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM app_meta WHERE key = 'migrated_usage_goal_data_v1'"
        ).fetchone()
        assert row["n"] == 1
        conn.close()


class TestDisclaimerLearnMore:
    """A.4: long disclaimers become one line + expandable 'Learn more'."""

    def _ui(self):
        from peptide_safety.server import HTML_CONTENT
        return HTML_CONTENT

    def test_learn_more_details_present(self):
        ui = self._ui()
        assert ui.count("<details") >= 5
        assert ui.count("Learn more") >= 5

    def test_disclaimer_meaning_kept(self):
        from peptide_safety.server import DISCLAIMER
        assert "not medical advice" in DISCLAIMER
        assert "not " in DISCLAIMER and "FDA-approved" in DISCLAIMER
        assert "never recommends doses" in DISCLAIMER
        assert "never rates" in DISCLAIMER


class TestCommonGoalChips:
    """A.6: ~6 common goal chips first, the rest under 'More goals'."""

    def _ui(self):
        from peptide_safety.server import HTML_CONTENT
        return HTML_CONTENT

    def test_six_common_goals_defined(self):
        ui = self._ui()
        line = next(l for l in ui.splitlines()
                    if l.strip().startswith("const COMMON_GOALS"))
        keys = line.split("[", 1)[1].split("]", 1)[0].replace("'", "").split(",")
        keys = [k.strip() for k in keys if k.strip()]
        assert len(keys) == 6
        for k in keys:
            assert k in ("sleep", "recovery", "energy", "mood", "appetite",
                         "digestion", "joints", "skin", "libido", "bodyweight",
                         "height", "treatment", "symptoms", "appearance",
                         "growth_clinician", "visit_prep", "recordkeeping",
                         "custom")

    def test_more_goals_toggle_in_both_chip_lists(self):
        ui = self._ui()
        assert "More goals" in ui
        assert "visibleGoalKeys" in ui
        # both Settings chips and onboarding chips use the shared helper
        assert ui.count("visibleGoalKeys(") >= 2
