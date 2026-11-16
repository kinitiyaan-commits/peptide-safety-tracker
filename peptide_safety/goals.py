"""Personal tracking goals.

AGENTS.md rule 3c and the catalog spec: goals customize the user's journal
fields only. They are NOT indications, effects, or treatment claims. Labels
describe what the user records; they never say a substance treats, cures, or
causes anything. Keep this registry separate from the sourced catalog
(clinical facts).

Each goal has a stable string key (never renumber or merge; historical
observations reference these keys via field keys), a human label, and zero or
more suggested journal fields. A goal without fields is an intent marker only.
"""

GOAL_FIELD_TYPES = ("rating", "number", "text")

# Required concise explanation from the catalog spec, shown in the UI.
GOALS_EXPLANATION = (
    "Your goals customize your journal, not medication recommendations. "
    "Recording a goal does not mean a product is effective or appropriate "
    "for it."
)

TRACKING_GOALS = {
    # ---- personal observations (granular journal fields) ----
    "sleep": {
        "label": "Sleep and energy observations",
        "fields": [
            {"key": "sleep_rating", "label": "Sleep quality (1–5)", "type": "rating"},
            {"key": "sleep_hours", "label": "Sleep duration (hours)", "type": "number"},
        ],
    },
    "recovery": {
        "label": "Training and recovery observations",
        "fields": [
            {"key": "recovery_rating", "label": "Recovery (1–5)", "type": "rating"},
            {"key": "activity_notes", "label": "Activity notes", "type": "text"},
        ],
    },
    "energy": {
        "label": "Energy levels",
        "field": {"key": "energy_rating", "label": "Energy (1–5)", "type": "rating"},
    },
    "mood": {
        "label": "Mood",
        "field": {"key": "mood_rating", "label": "Mood (1–5)", "type": "rating"},
    },
    "appetite": {
        "label": "Appetite",
        "field": {"key": "appetite_rating", "label": "Appetite (1–5)", "type": "rating"},
    },
    "digestion": {
        "label": "Digestive comfort",
        "field": {"key": "digestion_rating", "label": "Digestive comfort (1–5)", "type": "rating"},
    },
    "joints": {
        "label": "Joint comfort",
        "field": {"key": "joints_rating", "label": "Joint comfort (1–5)", "type": "rating"},
    },
    "skin": {
        "label": "Skin or hair observations",
        "fields": [
            {"key": "skin_rating", "label": "Skin (1–5)", "type": "rating"},
            {"key": "skin_notes", "label": "Skin/hair notes", "type": "text"},
        ],
    },
    "libido": {
        "label": "Libido",
        "field": {"key": "libido_rating", "label": "Libido (1–5)", "type": "rating"},
    },
    "bodyweight": {
        "label": "Weight or body-composition observations",
        "fields": [
            {"key": "bodyweight_kg", "label": "Body weight (kg)", "type": "number"},
            {"key": "waist_cm", "label": "Waist measurement (cm)", "type": "number"},
        ],
    },
    "height": {
        "label": "Height (plain measurement)",
        "field": {"key": "height_cm", "label": "Height (cm)", "type": "number"},
        "note": "Journal measurement only. See Learn → 'Growth hormone & height claims' "
                "for the sourced educational note.",
    },
    # ---- spec-suggested motivation labels ----
    "treatment": {
        "label": "Prescribed treatment and medication routine",
        "fields": [
            {"key": "treatment_context", "label": "Treatment context (your words)", "type": "text"},
            {"key": "visit_questions", "label": "Questions for the next visit", "type": "text"},
        ],
    },
    "symptoms": {
        # Intent marker: symptoms themselves are logged in the separate
        # Symptom section, which does not require naming a substance.
        "label": "Symptoms and side effects",
    },
    "appearance": {
        "label": "Appearance-related personal goals",
        "field": {"key": "appearance_notes", "label": "Private notes about your own goals",
                  "type": "text"},
        "note": "Private journal notes only — no attractiveness ratings, social "
                "comparison, or inferred defects.",
    },
    "growth_clinician": {
        "label": "Clinician-managed growth or hormone treatment",
        "fields": [
            {"key": "height_cm", "label": "Height (cm)", "type": "number"},
            {"key": "visit_notes", "label": "Clinician visit notes", "type": "text"},
        ],
        "note": "Optional user-recorded measurements and visit notes only — this app "
                "never predicts height gains or scores growth potential.",
    },
    "visit_prep": {
        "label": "Preparing records for a healthcare visit",
        "field": {"key": "visit_notes", "label": "Visit notes", "type": "text"},
    },
    "recordkeeping": {
        "label": "General recordkeeping",
    },
    "custom": {
        # The user's own wording lives in user_goals.custom_text (private).
        "label": "Custom reason (your own words)",
    },
}


def _goal_fields(goal):
    fields = []
    if "field" in goal:
        fields.append(goal["field"])
    fields.extend(goal.get("fields", []))
    return fields


def goal_field_keys(goal_keys):
    keys = []
    for gk in goal_keys:
        for field in _goal_fields(TRACKING_GOALS.get(gk, {})):
            keys.append(field)
    return keys


def validate_goal_data(goal_keys, goal_data):
    """Return a normalized goal_data dict or raise ValueError.

    Values must match the field types of the user's *enabled* goals, so
    journal data can never claim an effect tied to a substance. Historical
    entries are validated at write time only; later goal changes never
    rewrite or delete them.
    """
    import json

    if goal_data is None:
        return None
    if not isinstance(goal_data, dict):
        raise ValueError("goal_data must be a JSON object keyed by goal field")
    try:
        json.dumps(goal_data)
    except (TypeError, ValueError) as exc:
        raise ValueError("goal_data must be JSON-serializable") from exc
    if len(goal_data) > 20:
        raise ValueError("too many goal fields")

    allowed = {f["key"]: f for f in goal_field_keys(goal_keys)}
    cleaned = {}
    for key, value in goal_data.items():
        if key not in allowed:
            raise ValueError(f"goal field not enabled for this profile: {key}")
        ftype = allowed[key]["type"]
        if ftype == "rating":
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
                raise ValueError(f"{key} must be an integer rating 1-5")
        elif ftype == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{key} must be a number")
        else:  # text
            if not isinstance(value, str) or len(value) > 200:
                raise ValueError(f"{key} must be text of at most 200 characters")
        cleaned[key] = value
    return cleaned or None
