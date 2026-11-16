"""Service layer. Every user-data operation is explicitly scoped by user_id."""

import json
import sqlite3
from datetime import datetime, timezone

from . import ALLOWED_UNITS, SEVERITY_MIN, SEVERITY_MAX
from .db import connect, DEFAULT_DB_PATH


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_unit(unit):
    if unit not in ALLOWED_UNITS:
        raise ValueError(
            f"unit must be one of {', '.join(ALLOWED_UNITS)} (explicit units required)"
        )


def _validate_amount(amount):
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0:
        raise ValueError("amount must be a number greater than 0")


# ---------------------------------------------------------------- users ---

def _validate_age(age):
    if age in (None, ""):
        return None
    age = int(age)
    if not (1 <= age <= 120):
        raise ValueError("age must be between 1 and 120 (or left empty)")
    return age


def create_user(db_path, display_name, age=None, tracking_note="",
                consent_ack=False):
    name = str(display_name).strip()
    if not name:
        raise ValueError("display name is required")
    age = _validate_age(age)
    conn = connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (display_name, age, tracking_note, consent_ack, "
            "is_demo) VALUES (?, ?, ?, ?, 0)",
            (name, age, str(tracking_note).strip(),
             1 if consent_ack else 0),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"display name already exists: {name}") from exc
    finally:
        conn.close()


def update_user(db_path, user_id, age=None, tracking_note=None):
    conn = connect(db_path)
    cur = conn.cursor()
    if age is not None:
        cur.execute("UPDATE users SET age = ? WHERE id = ?",
                    (_validate_age(age), user_id))
    if tracking_note is not None:
        cur.execute("UPDATE users SET tracking_note = ? WHERE id = ?",
                    (str(tracking_note).strip(), user_id))
    conn.commit()
    updated = cur.rowcount
    conn.close()
    return updated == 1


def list_users(db_path):
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT id, display_name, is_demo, age, tracking_note, consent_ack "
        "FROM users ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ------------------------------------------------- tracking goals --------

def get_user_goals(db_path, user_id):
    """Return the user's goal keys in display order."""
    return [row["goal_key"] for row in get_user_goal_details(db_path, user_id)]


def get_user_goal_details(db_path, user_id):
    """Return [{goal_key, custom_text}] in display order."""
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT goal_key, custom_text FROM user_goals WHERE user_id = ? "
        "ORDER BY position, id",
        (user_id,),
    ).fetchall()
    conn.close()
    return [{"goal_key": r["goal_key"], "custom_text": r["custom_text"] or ""}
            for r in rows]


def set_user_goals(db_path, user_id, goal_keys, custom_texts=None):
    """Store goal selection (reversible; never touches logged data).

    goal_keys: list of stable goal keys.
    custom_texts: optional {goal_key: text}; currently used for the user's
    own wording of the 'custom' reason. Private, per-profile, escaped in UI.
    """
    from .goals import TRACKING_GOALS
    keys = list(dict.fromkeys(str(k).strip() for k in goal_keys))
    unknown = [k for k in keys if k not in TRACKING_GOALS]
    if unknown:
        raise ValueError(f"unknown goal key(s): {', '.join(unknown)}")
    custom_texts = {
        str(k).strip(): str(v).strip()[:200]
        for k, v in (custom_texts or {}).items()
        if str(v).strip()
    }
    bad_custom = [k for k in custom_texts if k not in TRACKING_GOALS]
    if bad_custom:
        raise ValueError(f"unknown goal key(s): {', '.join(bad_custom)}")
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM user_goals WHERE user_id = ?", (user_id,))
    for pos, key in enumerate(keys):
        cur.execute(
            "INSERT INTO user_goals (user_id, goal_key, custom_text, position) "
            "VALUES (?, ?, ?, ?)",
            (user_id, key, custom_texts.get(key, ""), pos),
        )
    conn.commit()
    conn.close()
    return keys


# --------------------------------------------------------------- usage ----

DUPLICATE_WINDOW_SECONDS = 120


class DuplicateUsageError(ValueError):
    """A near-identical entry was just recorded for this profile."""


def _parse_iso(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None


def check_recent_duplicate(conn, user_id, peptide_name, amount, unit, taken_at,
                           window_seconds=DUPLICATE_WINDOW_SECONDS):
    """Server-side duplicate guard (spec: not just a disabled submit button).

    Raises DuplicateUsageError when the same profile already recorded the same
    product, amount, and unit within the window around taken_at. Deliberate
    overrides pass allow_duplicate=True and are never blocked.
    """
    ts = _parse_iso(taken_at)
    if ts is None:
        return  # nothing comparable; validation of taken_at happens upstream
    rows = conn.execute(
        "SELECT id, taken_at, amount, unit FROM usage_log "
        "WHERE user_id = ? AND LOWER(TRIM(peptide_name)) = LOWER(TRIM(?)) "
        "AND unit = ? AND ABS(amount - ?) < 1e-9 "
        "ORDER BY id DESC LIMIT 10",
        (user_id, peptide_name, unit, float(amount)),
    ).fetchall()
    for row in rows:
        other = _parse_iso(row["taken_at"])
        if other is None:
            continue
        if other.tzinfo is None:
            other = other.replace(tzinfo=timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if abs((ts - other).total_seconds()) <= window_seconds:
            raise DuplicateUsageError(
                f"Possible duplicate: {peptide_name} {amount} {unit} was "
                f"already recorded at {row['taken_at']}."
            )


def log_usage(db_path, user_id, peptide_name, amount, unit, route="unspecified",
              brand_id=None, taken_at=None, notes="", goal_data=None,
              allow_duplicate=False):
    _validate_amount(amount)
    _validate_unit(unit)
    if not peptide_name or not str(peptide_name).strip():
        raise ValueError("peptide_name is required")
    taken_at = taken_at or _now_iso()
    from .goals import validate_goal_data
    goal_json = None
    cleaned_goal_data = validate_goal_data(get_user_goals(db_path, user_id), goal_data)
    if cleaned_goal_data is not None:
        goal_json = json.dumps(cleaned_goal_data)
    conn = connect(db_path)
    try:
        if not allow_duplicate:
            check_recent_duplicate(conn, user_id, peptide_name, amount, unit, taken_at)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO usage_log (user_id, peptide_name, amount, unit, route, "
            "brand_id, taken_at, notes, goal_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, peptide_name.strip(), float(amount), unit, route,
             brand_id, taken_at, notes, goal_json),
        )
        conn.commit()
        entry_id = cur.lastrowid
    finally:
        conn.close()
    return entry_id


def list_usage(db_path, user_id):
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT u.*, b.name AS brand_name FROM usage_log u "
        "LEFT JOIN brands b ON b.id = u.brand_id "
        "WHERE u.user_id = ? ORDER BY u.taken_at DESC, u.id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        entry = dict(r)
        raw = entry.get("goal_data")
        entry["goal_data"] = json.loads(raw) if raw else None
        raw = entry.get("corrections")
        entry["corrections"] = json.loads(raw) if raw else []
        out.append(entry)
    return out


def delete_usage(db_path, user_id, entry_id):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM usage_log WHERE user_id = ? AND id = ?",
                (user_id, entry_id))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return deleted == 1


# ------------------------------------------------------------- edits ------
# Corrections (spec: "Explain and test how corrections are recorded"):
# each edit appends {edited_at, previous:{...}} to the row's corrections
# list, preserving original and intermediate values plus timestamps.
# The row is never overwritten destructively; deletes remain explicit.

EDITABLE_USAGE_FIELDS = ("peptide_name", "amount", "unit", "route",
                         "taken_at", "notes")
EDITABLE_OBSERVATION_FIELDS = ("taken_at", "notes", "goal_data")


def _correction_entry(previous):
    return {"edited_at": _now_iso(), "previous": previous}


def edit_usage(db_path, user_id, entry_id, updates):
    """Correct a usage entry; append a correction record with the prior values.

    updates: dict limited to EDITABLE_USAGE_FIELDS. Validated exactly like a
    new entry (amount > 0, explicit unit, taken_at present). goal_data and
    brand_id are not editable here (goal changes are history, not corrections).
    """
    bad = [k for k in updates if k not in EDITABLE_USAGE_FIELDS]
    if bad:
        raise ValueError(f"fields not editable: {', '.join(bad)}")
    if not updates:
        raise ValueError("no changes supplied")
    conn = connect(db_path)
    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT * FROM usage_log WHERE user_id = ? AND id = ?",
            (user_id, entry_id),
        ).fetchone()
        if row is None:
            raise ValueError("entry not found for this user")
        previous = {}   # old values of fields that actually change
        new_values = {} # validated new values to write
        if "peptide_name" in updates:
            name = str(updates["peptide_name"]).strip()
            if not name:
                raise ValueError("peptide_name is required")
            if name != row["peptide_name"]:
                previous["peptide_name"] = row["peptide_name"]
                new_values["peptide_name"] = name
        if "amount" in updates:
            _validate_amount(updates["amount"])
            amount = float(updates["amount"])
            if amount != row["amount"]:
                previous["amount"] = row["amount"]
                new_values["amount"] = amount
        if "unit" in updates:
            _validate_unit(updates["unit"])
            if updates["unit"] != row["unit"]:
                previous["unit"] = row["unit"]
                new_values["unit"] = updates["unit"]
        if "route" in updates and updates["route"] != row["route"]:
            previous["route"] = row["route"]
            new_values["route"] = str(updates["route"])
        if "taken_at" in updates:
            taken = str(updates["taken_at"] or "").strip()
            if not taken:
                raise ValueError("taken_at is required")
            if taken != row["taken_at"]:
                previous["taken_at"] = row["taken_at"]
                new_values["taken_at"] = taken
        if "notes" in updates:
            notes = str(updates["notes"] or "")
            if notes != row["notes"]:
                previous["notes"] = row["notes"]
                new_values["notes"] = notes
        if not previous:
            return False  # nothing actually changed; no correction recorded
        corrections = json.loads(row["corrections"]) if row["corrections"] else []
        corrections.append(_correction_entry(previous))
        sets = ", ".join(f"{k} = ?" for k in new_values)
        params = [new_values[k] for k in new_values]
        cur.execute(
            f"UPDATE usage_log SET {sets}, corrections = ? "
            "WHERE user_id = ? AND id = ?",
            (*params, json.dumps(corrections), user_id, entry_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def edit_observation(db_path, user_id, entry_id, updates):
    """Correct an observation (taken_at / notes / goal measurements).

    goal_data corrections are validated against the profile's enabled goals
    like a fresh entry; the previous measurement set is preserved in the
    correction record.
    """
    bad = [k for k in updates if k not in EDITABLE_OBSERVATION_FIELDS]
    if bad:
        raise ValueError(f"fields not editable: {', '.join(bad)}")
    if not updates:
        raise ValueError("no changes supplied")
    conn = connect(db_path)
    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT * FROM observations WHERE user_id = ? AND id = ?",
            (user_id, entry_id),
        ).fetchone()
        if row is None:
            raise ValueError("entry not found for this user")
        previous = {}
        new_values = {}
        if "taken_at" in updates:
            taken = str(updates["taken_at"] or "").strip()
            if not taken:
                raise ValueError("taken_at is required")
            if taken != row["taken_at"]:
                previous["taken_at"] = row["taken_at"]
                new_values["taken_at"] = taken
        if "notes" in updates:
            notes = str(updates["notes"] or "")
            if notes != row["notes"]:
                previous["notes"] = row["notes"]
                new_values["notes"] = notes
        if "goal_data" in updates:
            from .goals import validate_goal_data
            cleaned = validate_goal_data(
                get_user_goals(db_path, user_id), updates["goal_data"])
            new_json = json.dumps(cleaned) if cleaned else None
            if new_json != row["goal_data"]:
                previous["goal_data"] = (
                    json.loads(row["goal_data"]) if row["goal_data"] else None)
                new_values["goal_data"] = new_json
        if not previous:
            return False
        corrections = json.loads(row["corrections"]) if row["corrections"] else []
        corrections.append(_correction_entry(previous))
        sets = ", ".join(f"{k} = ?" for k in new_values)
        params = [new_values[k] for k in new_values]
        cur.execute(
            f"UPDATE observations SET {sets}, corrections = ? "
            "WHERE user_id = ? AND id = ?",
            (*params, json.dumps(corrections), user_id, entry_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


# -------------------------------------------------------- idempotency -----

def get_idempotent_response(db_path, user_id, idem_key):
    """Return the stored response for a client idempotency key, or None.

    Distinct from the suspected-duplicate guard: the duplicate guard asks
    "did you already log this?" (409, override allowed); idempotency asks
    "is this the *same submission* being retried?" — a retry replays the
    original response and never creates another event.
    """
    if not idem_key or not str(idem_key).strip():
        return None
    conn = connect(db_path)
    row = conn.execute(
        "SELECT response_json FROM idempotency_keys "
        "WHERE user_id = ? AND idem_key = ?",
        (user_id, str(idem_key).strip()),
    ).fetchone()
    conn.close()
    return json.loads(row["response_json"]) if row else None


def record_idempotency(db_path, user_id, idem_key, scope, response):
    """Store a response against a client idempotency key (after success)."""
    if not idem_key or not str(idem_key).strip():
        return
    conn = connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO idempotency_keys "
        "(user_id, idem_key, scope, response_json) VALUES (?, ?, ?, ?)",
        (user_id, str(idem_key).strip(), scope, json.dumps(response)),
    )
    conn.commit()
    conn.close()


# ------------------------------------------------------------- symptoms ---

def log_symptom(db_path, user_id, peptide_name, severity, description,
                logged_at=None):
    if not isinstance(severity, int) or not (SEVERITY_MIN <= severity <= SEVERITY_MAX):
        raise ValueError(f"severity must be an integer {SEVERITY_MIN}-{SEVERITY_MAX}")
    if not description or not str(description).strip():
        raise ValueError("description is required")
    if not peptide_name or not str(peptide_name).strip():
        raise ValueError("peptide_name is required")
    logged_at = logged_at or _now_iso()
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO symptoms (user_id, peptide_name, severity, description, "
        "logged_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, peptide_name.strip(), severity, description.strip(), logged_at),
    )
    conn.commit()
    entry_id = cur.lastrowid
    conn.close()
    return entry_id


def list_symptoms(db_path, user_id):
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT * FROM symptoms WHERE user_id = ? ORDER BY logged_at DESC, id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_symptom(db_path, user_id, entry_id):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM symptoms WHERE user_id = ? AND id = ?",
                (user_id, entry_id))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return deleted == 1


# --------------------------------------------------------- observations ---

def log_observation(db_path, user_id, taken_at=None, notes="", goal_data=None):
    """Record a goal measurement WITHOUT any administration event.

    Same validation as usage goal_data: values must belong to the profile's
    enabled goals. This is the spec's independent-logging requirement.
    """
    taken_at = taken_at or _now_iso()
    from .goals import validate_goal_data
    cleaned = validate_goal_data(get_user_goals(db_path, user_id), goal_data)
    if cleaned is None:
        raise ValueError(
            "an observation needs at least one enabled goal field "
            "(or use notes-only symptoms)"
        )
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO observations (user_id, taken_at, notes, goal_data) "
        "VALUES (?, ?, ?, ?)",
        (user_id, taken_at, notes or "", json.dumps(cleaned)),
    )
    conn.commit()
    entry_id = cur.lastrowid
    conn.close()
    return entry_id


def list_observations(db_path, user_id):
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT * FROM observations WHERE user_id = ? "
        "ORDER BY taken_at DESC, id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        entry = dict(r)
        raw = entry.get("goal_data")
        entry["goal_data"] = json.loads(raw) if raw else None
        raw = entry.get("corrections")
        entry["corrections"] = json.loads(raw) if raw else []
        out.append(entry)
    return out


def delete_observation(db_path, user_id, entry_id):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM observations WHERE user_id = ? AND id = ?",
                (user_id, entry_id))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return deleted == 1


# ------------------------------------------------------------ reminders ---

def add_reminder(db_path, user_id, peptide_name, time_of_day, days,
                 notes="", enabled=True):
    if not peptide_name or not str(peptide_name).strip():
        raise ValueError("peptide_name is required")
    if not days or not str(days).strip():
        raise ValueError("days is required (e.g. Mon,Fri or Daily)")
    normalized = str(time_of_day).strip()
    if not _valid_time(normalized):
        raise ValueError("time_of_day must be HH:MM in 24-hour format")
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reminders (user_id, peptide_name, time_of_day, days, "
        "notes, enabled) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, peptide_name.strip(), normalized, str(days).strip(),
         notes, 1 if enabled else 0),
    )
    conn.commit()
    entry_id = cur.lastrowid
    conn.close()
    return entry_id


def _valid_time(value):
    if not isinstance(value, str) or ":" not in value:
        return False
    hh, mm = value.split(":", 1)
    if len(hh) > 2 or len(mm) != 2:
        return False
    return hh.isdigit() and mm.isdigit() and int(hh) <= 23 and int(mm) <= 59


def list_reminders(db_path, user_id):
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT * FROM reminders WHERE user_id = ? ORDER BY time_of_day, id",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_reminder_enabled(db_path, user_id, entry_id, enabled):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("UPDATE reminders SET enabled = ? WHERE user_id = ? AND id = ?",
                (1 if enabled else 0, user_id, entry_id))
    conn.commit()
    updated = cur.rowcount
    conn.close()
    return updated == 1


def delete_reminder(db_path, user_id, entry_id):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM reminders WHERE user_id = ? AND id = ?",
                (user_id, entry_id))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return deleted == 1


# ------------------------------------------------- saved products --------

def save_product(db_path, user_id, name, default_unit=None, notes=""):
    name = str(name).strip()
    if not name:
        raise ValueError("product name is required")
    if len(name) > 120:
        raise ValueError("product name is too long (max 120 characters)")
    if default_unit is not None and default_unit != "":
        _validate_unit(default_unit)
        default_unit = str(default_unit)
    else:
        default_unit = None
    conn = connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO saved_products (user_id, name, default_unit, notes) "
            "VALUES (?, ?, ?, ?)",
            (user_id, name, default_unit, str(notes).strip()),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"product already saved: {name}") from exc
    finally:
        conn.close()


def list_products(db_path, user_id):
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT * FROM saved_products WHERE user_id = ? ORDER BY name COLLATE NOCASE",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_product(db_path, user_id, product_id):
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM saved_products WHERE user_id = ? AND id = ?",
                (user_id, product_id))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return deleted == 1


# ------------------------------------------------- catalog and brands -----

def list_catalog(db_path):
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT * FROM catalog ORDER BY regulatory_status, name"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        entry = dict(r)
        raw = entry.get("aliases")
        entry["aliases"] = json.loads(raw) if raw else []
        out.append(entry)
    return out


def list_brands(db_path):
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT * FROM brands ORDER BY name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_brand(db_path, name, supplier_type, region="unspecified", notes=""):
    allowed = ("pharma", "compounding-pharmacy", "research-supplier", "other")
    if supplier_type not in allowed:
        raise ValueError(f"supplier_type must be one of {', '.join(allowed)}")
    if not name or not str(name).strip():
        raise ValueError("name is required")
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO brands (name, supplier_type, region, notes, is_demo) "
        "VALUES (?, ?, ?, ?, 0)",
        (name.strip(), supplier_type, region, notes),
    )
    conn.commit()
    brand_id = cur.lastrowid
    conn.close()
    return brand_id


# ------------------------------------------------- verification links ----
# Neutral link-outs only (AGENTS.md rules 3 and 11): the app constructs
# search URLs; it never interprets or summarizes the results.

def verification_links(product_name):
    from urllib.parse import quote
    q = quote(str(product_name), safe="")
    return {
        "dailymed_label_search":
            "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=" + q,
        "openfda_drug_records":
            "https://open.fda.gov/data/drug/",
        "fda_compounding_page":
            "https://www.fda.gov/drugs/human-drug-compounding",
        "fda_buying_medicine_online":
            "https://www.fda.gov/consumers/buying-medicine-online",
        "disclaimer":
            "Links only. This app does not interpret results and never "
            "rates a brand as safe or unsafe. Verify licensure and "
            "prescription requirements yourself.",
    }


# ------------------------------------------------------------- migrations ---

USAGE_GOAL_MIGRATION_KEY = "migrated_usage_goal_data_v1"


def migrate_usage_goal_data_to_observations(db_path=DEFAULT_DB_PATH):
    """Move goal measurements out of dose entries into linked observations.

    Goal fields were removed from the dose form (they belong only in
    Observations). This one-time migration preserves every existing
    usage_log.goal_data value by copying it — untouched and unvalidated
    against the profile's *current* goals, so nothing is lost even if the
    user has since disabled that goal — into a new observation row taken at
    the same timestamp, with a marker note linking it back to the dose
    entry. The original usage rows are left exactly as they were
    (non-destructive); the migrated measurement now lives in Observations
    where it belongs.

    Idempotent: guarded by an app_meta marker, so running it again (server
    restarts, tests) never creates duplicates.
    """
    conn = connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT value FROM app_meta WHERE key = ?",
                (USAGE_GOAL_MIGRATION_KEY,))
    if cur.fetchone():
        conn.close()
        return 0
    created = 0
    rows = cur.execute(
        "SELECT id, user_id, peptide_name, taken_at, goal_data "
        "FROM usage_log WHERE goal_data IS NOT NULL ORDER BY id"
    ).fetchall()
    for r in rows:
        try:
            goal_data = json.loads(r["goal_data"])
        except (TypeError, ValueError):
            continue
        if not goal_data:
            continue
        note = ("Migrated from dose entry #%d (%s): goal measurements moved "
                "to Observations." % (r["id"], r["peptide_name"]))
        cur.execute(
            "INSERT INTO observations (user_id, taken_at, notes, goal_data) "
            "VALUES (?, ?, ?, ?)",
            (r["user_id"], r["taken_at"], note,
             json.dumps(goal_data)),
        )
        created += 1
    cur.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?)",
        (USAGE_GOAL_MIGRATION_KEY, _now_iso()),
    )
    conn.commit()
    conn.close()
    return created
