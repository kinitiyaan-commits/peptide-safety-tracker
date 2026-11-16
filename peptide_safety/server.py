"""FastAPI server for the peptide safety app (run separately from app.py).

    python -m peptide_safety.server          # port 8001

Local-first: all health data lives in peptide_safety.db next to this repo.
"""

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.responses import HTMLResponse, Response

from . import service, __version__
from .db import DEFAULT_DB_PATH
from .exporters import export_user_data
from .seed import seed_demo

DB_PATH = DEFAULT_DB_PATH


@asynccontextmanager
async def lifespan(_app):
    ensure_seeded()
    yield


app = FastAPI(title="Peptide Safety — Milestone A",
              version=__version__, lifespan=lifespan)

seeded_user_id = None


def ensure_seeded():
    global seeded_user_id
    if seeded_user_id is None:
        seeded_user_id = seed_demo(DB_PATH)
        # One-time migration: goal measurements that were recorded on dose
        # entries (goal fields are removed from the dose form) move into
        # linked Observations rows. Idempotent, non-destructive.
        from .service import migrate_usage_goal_data_to_observations
        migrate_usage_goal_data_to_observations(DB_PATH)
    return seeded_user_id


# ------------------------------------------------------------ UI ----------

@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_CONTENT


# ------------------------------------------------------------ users -------

@app.get("/api/users")
def api_users():
    ensure_seeded()
    return {"users": service.list_users(DB_PATH)}


@app.post("/api/users")
def api_create_user(body: dict = Body(...)):
    try:
        user_id = service.create_user(
            DB_PATH,
            display_name=str(body.get("display_name", "")),
            age=body.get("age"),
            tracking_note=str(body.get("tracking_note", "")),
            consent_ack=bool(body.get("consent_ack", False)),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"user_id": user_id}


@app.patch("/api/users/{user_id}")
def api_update_user(user_id: int, body: dict = Body(...)):
    try:
        ok = service.update_user(
            DB_PATH, user_id,
            age=body.get("age"),
            tracking_note=(None if "tracking_note" not in body
                           else str(body["tracking_note"])),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not ok:
        raise HTTPException(404, "user not found")
    return {"updated": True}


# ------------------------------------------------- tracking goals ---------

@app.get("/api/goals/registry")
def api_goal_registry():
    from .goals import TRACKING_GOALS
    return {"goals": TRACKING_GOALS}


@app.get("/api/goals/{user_id}")
def api_user_goals(user_id: int):
    return {
        "goals": service.get_user_goals(DB_PATH, user_id),
        "details": service.get_user_goal_details(DB_PATH, user_id),
    }


@app.put("/api/goals/{user_id}")
def api_set_goals(user_id: int, body: dict = Body(...)):
    try:
        keys = service.set_user_goals(
            DB_PATH, user_id, body.get("goals", []),
            custom_texts=body.get("custom_texts"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"goals": keys}


# --------------------------------------------------- saved products -------

@app.get("/api/products/{user_id}")
def api_products(user_id: int):
    return {"products": service.list_products(DB_PATH, user_id)}


@app.post("/api/products/{user_id}")
def api_save_product(user_id: int, body: dict = Body(...)):
    try:
        product_id = service.save_product(
            DB_PATH, user_id,
            name=str(body.get("name", "")),
            default_unit=body.get("default_unit"),
            notes=str(body.get("notes", "")),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"product_id": product_id}


@app.delete("/api/products/{user_id}/{product_id}")
def api_delete_product(user_id: int, product_id: int):
    if not service.delete_product(DB_PATH, user_id, product_id):
        raise HTTPException(404, "product not found for this user")
    return {"deleted": True}


# -------------------------------------------------------- demo data -------

@app.post("/api/demo/reset")
def api_demo_reset():
    """Restore the synthetic demo profile to its original sample records."""
    ensure_seeded()
    demo_id = seed_demo(DB_PATH)
    return {"demo_user_id": demo_id, "reset": True}


@app.get("/api/catalog")
def api_catalog():
    return {"catalog": service.list_catalog(DB_PATH)}


@app.get("/api/brands")
def api_brands():
    return {"brands": service.list_brands(DB_PATH)}


@app.post("/api/brands")
def api_add_brand(body: dict = Body(...)):
    try:
        brand_id = service.add_brand(
            DB_PATH,
            name=str(body.get("name", "")),
            supplier_type=str(body.get("supplier_type", "")),
            region=str(body.get("region", "unspecified")),
            notes=str(body.get("notes", "")),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"brand_id": brand_id}


@app.get("/api/verify")
def api_verify(name: str = Query(..., min_length=1)):
    """Neutral verification link-outs; no interpretation (AGENTS.md rule 11)."""
    return {"product": name, "links": service.verification_links(name)}


# -------------------------------------------------------- user data -------

@app.get("/api/usage/{user_id}")
def api_usage(user_id: int):
    return {"usage": service.list_usage(DB_PATH, user_id)}


@app.post("/api/usage/{user_id}")
def api_log_usage(user_id: int, body: dict = Body(...)):
    # Idempotency (distinct from the duplicate guard): a retried submission
    # carrying the same client key replays the original response and never
    # creates another event.
    idem_key = body.get("idempotency_key")
    stored = service.get_idempotent_response(DB_PATH, user_id, idem_key)
    if stored is not None:
        return {**stored, "replayed": True}
    try:
        entry_id = service.log_usage(
            DB_PATH, user_id,
            peptide_name=str(body.get("peptide_name", "")),
            amount=body.get("amount"),
            unit=str(body.get("unit", "")),
            route=str(body.get("route", "unspecified")),
            brand_id=body.get("brand_id"),
            taken_at=body.get("taken_at"),
            notes=str(body.get("notes", "")),
            goal_data=body.get("goal_data"),
            allow_duplicate=bool(body.get("override_duplicate", False)),
        )
    except service.DuplicateUsageError as exc:
        # Server-side duplicate guard: prompt, but never block an
        # intentional override (usability spec).
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    response = {"entry_id": entry_id, "replayed": False}
    service.record_idempotency(DB_PATH, user_id, idem_key, "usage", response)
    return response


@app.patch("/api/usage/{user_id}/{entry_id}")
def api_edit_usage(user_id: int, entry_id: int, body: dict = Body(...)):
    try:
        changed = service.edit_usage(DB_PATH, user_id, entry_id, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"changed": changed}


# ----------------------------------------------------- observations -------
# Independent logging: goal measurements with no administration event.

@app.get("/api/observations/{user_id}")
def api_observations(user_id: int):
    return {"observations": service.list_observations(DB_PATH, user_id)}


@app.post("/api/observations/{user_id}")
def api_log_observation(user_id: int, body: dict = Body(...)):
    idem_key = body.get("idempotency_key")
    stored = service.get_idempotent_response(DB_PATH, user_id, idem_key)
    if stored is not None:
        return {**stored, "replayed": True}
    try:
        entry_id = service.log_observation(
            DB_PATH, user_id,
            taken_at=body.get("taken_at"),
            notes=str(body.get("notes", "")),
            goal_data=body.get("goal_data"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    response = {"entry_id": entry_id, "replayed": False}
    service.record_idempotency(DB_PATH, user_id, idem_key, "observation", response)
    return response


@app.patch("/api/observations/{user_id}/{entry_id}")
def api_edit_observation(user_id: int, entry_id: int, body: dict = Body(...)):
    try:
        changed = service.edit_observation(DB_PATH, user_id, entry_id, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"changed": changed}


@app.delete("/api/observations/{user_id}/{entry_id}")
def api_delete_observation(user_id: int, entry_id: int):
    if not service.delete_observation(DB_PATH, user_id, entry_id):
        raise HTTPException(404, "observation not found for this user")
    return {"deleted": True}


@app.delete("/api/usage/{user_id}/{entry_id}")
def api_delete_usage(user_id: int, entry_id: int):
    if not service.delete_usage(DB_PATH, user_id, entry_id):
        raise HTTPException(404, "entry not found for this user")
    return {"deleted": True}


@app.get("/api/symptoms/{user_id}")
def api_symptoms(user_id: int):
    return {"symptoms": service.list_symptoms(DB_PATH, user_id)}


@app.post("/api/symptoms/{user_id}")
def api_log_symptom(user_id: int, body: dict = Body(...)):
    try:
        entry_id = service.log_symptom(
            DB_PATH, user_id,
            peptide_name=str(body.get("peptide_name", "")),
            severity=body.get("severity"),
            description=str(body.get("description", "")),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"entry_id": entry_id}


@app.delete("/api/symptoms/{user_id}/{entry_id}")
def api_delete_symptom(user_id: int, entry_id: int):
    if not service.delete_symptom(DB_PATH, user_id, entry_id):
        raise HTTPException(404, "entry not found for this user")
    return {"deleted": True}


@app.get("/api/reminders/{user_id}")
def api_reminders(user_id: int):
    return {"reminders": service.list_reminders(DB_PATH, user_id)}


@app.post("/api/reminders/{user_id}")
def api_add_reminder(user_id: int, body: dict = Body(...)):
    try:
        entry_id = service.add_reminder(
            DB_PATH, user_id,
            peptide_name=str(body.get("peptide_name", "")),
            time_of_day=str(body.get("time_of_day", "")),
            days=str(body.get("days", "")),
            notes=str(body.get("notes", "")),
            enabled=bool(body.get("enabled", True)),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"entry_id": entry_id}


@app.patch("/api/reminders/{user_id}/{entry_id}")
def api_toggle_reminder(user_id: int, entry_id: int, body: dict = Body(...)):
    if not service.set_reminder_enabled(DB_PATH, user_id, entry_id,
                                        bool(body.get("enabled", True))):
        raise HTTPException(404, "reminder not found for this user")
    return {"updated": True}


@app.delete("/api/reminders/{user_id}/{entry_id}")
def api_delete_reminder(user_id: int, entry_id: int):
    if not service.delete_reminder(DB_PATH, user_id, entry_id):
        raise HTTPException(404, "reminder not found for this user")
    return {"deleted": True}


# --------------------------------------------------------- export ---------

@app.get("/api/export/{user_id}")
def api_export(user_id: int, fmt: str = Query("json", pattern="^(json|csv)$")):
    payload, media_type, filename = export_user_data(DB_PATH, user_id, fmt)
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


DISCLAIMER = (
    "This app is not medical advice. Many research peptides are not "
    "FDA-approved; compounded copies carry FDA-documented risks. The app "
    "records what you enter, never recommends doses, and never rates "
    "brands as safe or unsafe."
)

HTML_CONTENT = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Peptide Safety Tracker</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
body{font-family:system-ui,sans-serif;background:#020617}
.card{background:#0f172a;border:1px solid #1e293b;border-radius:1rem}
.inp{width:100%;background:#1e293b;border:1px solid #334155;border-radius:.5rem;padding:.7rem .85rem;font-size:.95rem;color:#e2e8f0}
.inp:focus{outline:none;border-color:#10b981}
.btn{background:linear-gradient(135deg,#059669,#10b981);color:#fff;font-weight:700;border-radius:.6rem;padding:.75rem 1.25rem;font-size:.9rem;transition:filter .15s}
.btn:hover{filter:brightness(1.12)}
.btn2{background:#1e293b;color:#e2e8f0;font-weight:600;border-radius:.6rem;padding:.75rem 1.25rem;font-size:.9rem;border:1px solid #334155}
.btn2:hover{background:#334155}
details>summary{cursor:pointer;list-style:none}
details>summary::-webkit-details-marker{display:none}
.bottomnav{position:fixed;bottom:0;left:0;right:0;z-50;background:rgba(2,6,23,.97);border-top:1px solid #1e293b;backdrop-filter:blur(8px)}
.navbtn{flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;padding:.55rem 0 .7rem;font-size:.7rem;font-weight:600;color:#64748b;transition:color .15s}
.navbtn.active{color:#34d399}
.fab{width:3.6rem;height:3.6rem;border-radius:9999px;background:linear-gradient(135deg,#059669,#10b981);display:flex;align-items:center;justify-content:center;font-size:1.7rem;font-weight:700;color:#fff;margin-top:-1.6rem;border:4px solid #020617;box-shadow:0 8px 20px rgba(16,185,129,.35)}
.picker-wrap{position:relative}
/* Opens upward so it never covers the Amount / Unit fields below (A.5). */
.picker-list{position:absolute;left:0;right:0;bottom:100%;margin-bottom:.3rem;z-index:70;background:#0f172a;border:1px solid #334155;border-radius:.6rem;max-height:15rem;overflow-y:auto;box-shadow:0 12px 30px rgba(0,0,0,.5)}
.dd-item{padding:.65rem .85rem;font-size:.9rem;cursor:pointer;display:flex;justify-content:space-between;gap:.5rem;align-items:center}
.dd-item:hover,.dd-item.hl{background:#1e293b}
.dd-item .src{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#64748b;white-space:nowrap}
.chip{display:inline-flex;align-items:center;gap:.35rem;background:#1e293b;border:1px solid #334155;color:#a7f3d0;border-radius:9999px;padding:.35rem .8rem;font-size:.8rem;font-weight:600;cursor:pointer}
.chip:hover{border-color:#10b981}
#toast{position:fixed;left:50%;transform:translateX(-50%);bottom:6.2rem;z-index:80;background:#064e3b;border:1px solid #10b981;color:#d1fae5;padding:.7rem 1.1rem;border-radius:.7rem;font-size:.85rem;font-weight:600;display:flex;align-items:center;gap:.5rem;opacity:0;pointer-events:none;transition:opacity .2s}
#toast.show{opacity:1}
#toast.err{background:#450a0a;border-color:#f87171;color:#fecaca}
.err{display:none;color:#f87171;font-size:.8rem;margin-top:.25rem}
.err.show{display:block}
.invalid{border-color:#f87171 !important}
</style>
</head>
<body class="text-slate-100 min-h-screen pb-24">

<div id="toast"></div>

<!-- ============ START / ONBOARDING SCREEN ============ -->
<div id="screen-start" class="hidden min-h-screen flex items-center justify-center p-4 bg-gradient-to-b from-slate-950 via-slate-900 to-emerald-950/30">
  <div class="card max-w-lg w-full p-8 space-y-6 shadow-2xl">
    <div class="flex items-center gap-3">
      <div class="w-12 h-12 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-xl flex items-center justify-center font-black text-2xl">P</div>
      <div>
        <h1 class="text-2xl font-black tracking-tight">Peptide Safety Tracker</h1>
        <p class="text-sm text-slate-400">Track what you use. Understand the evidence. Bring better records to your clinician.</p>
      </div>
    </div>

    <div class="flex gap-2">
      <div class="h-1.5 flex-1 rounded-full bg-emerald-500" id="dot-1"></div>
      <div class="h-1.5 flex-1 rounded-full bg-slate-700" id="dot-2"></div>
      <div class="h-1.5 flex-1 rounded-full bg-slate-700" id="dot-3"></div>
      <div class="h-1.5 flex-1 rounded-full bg-slate-700" id="dot-4"></div>
    </div>

    <div id="ob-step-1" class="space-y-4">
      <h2 class="text-xl font-bold">Welcome — read this first</h2>
      <p class="text-sm text-slate-300 leading-relaxed">This app helps you <strong>log</strong> what you take, note <strong>symptoms</strong>, set your own <strong>reminders</strong>, and check <strong>regulatory status</strong> against official FDA / DailyMed sources.</p>
      <div class="bg-amber-950/40 border border-amber-800 rounded-xl p-4 text-sm text-amber-100 leading-relaxed">
        <p><strong>It is not medical advice</strong> — it never recommends doses or rates brands, and many research peptides are not FDA-approved.</p>
        <details class="mt-1"><summary class="text-amber-300 underline">Learn more</summary>
          <p class="pt-1 text-amber-200/90">Compounded copies of these substances carry FDA-documented risks. Nothing here is an endorsement of any substance. Talk to a licensed clinician before making any health decision, and verify anything important with official FDA / DailyMed sources.</p>
        </details>
      </div>
      <label class="flex items-start gap-3 text-sm cursor-pointer bg-slate-900 border border-slate-800 rounded-xl p-4">
        <input type="checkbox" id="ob-consent" class="mt-1 w-5 h-5 accent-emerald-500">
        <span>I understand this app is not medical advice and I will verify anything important with official sources and a healthcare professional.</span>
      </label>
      <button onclick="obGoto(2)" id="ob-next-1" class="btn w-full disabled:opacity-40 disabled:cursor-not-allowed" disabled>Continue</button>
    </div>

    <div id="ob-step-2" class="space-y-4 hidden">
      <h2 class="text-xl font-bold">Create your profile</h2>
      <p class="text-sm text-slate-400">Everything is stored <strong>locally on this device</strong>, in a local database file served by this app. Nothing is sent to any external server. Note: profiles are labels, not passwords — anyone using this device can open any profile.</p>
      <div><label class="block text-sm text-slate-400 mb-1">Profile name *</label>
        <input id="ob-name" class="inp" placeholder="e.g., Alex"></div>
      <div class="grid grid-cols-2 gap-3">
        <div><label class="block text-sm text-slate-400 mb-1">Age (optional)</label>
          <input id="ob-age" type="number" min="1" max="120" class="inp" placeholder="e.g., 34"></div>
        <div><label class="block text-sm text-slate-400 mb-1">What are you tracking?</label>
          <input id="ob-note" class="inp" placeholder="e.g., recovery stack"></div>
      </div>
      <div class="flex gap-2">
        <button onclick="obGoto(1)" class="btn2 flex-1">Back</button>
        <button onclick="obGoto(3)" id="ob-next-2" class="btn flex-1 disabled:opacity-40" disabled>Continue</button>
      </div>
    </div>

    <div id="ob-step-3" class="space-y-4 hidden">
      <h2 class="text-xl font-bold">What would you like to track?</h2>
      <p class="text-sm text-slate-300 leading-relaxed">Optional — pick any that fit. Your goals customize your journal, not medication recommendations. Recording a goal does not mean a product is effective or appropriate for it. These are personal journal fields, never clinical indications; you can change them anytime in Settings → Tracking goals.</p>
      <div id="ob-goal-chips" class="flex flex-wrap gap-2 max-h-56 overflow-y-auto"></div>
      <p class="text-xs text-slate-500">Everything here stays per profile, on this device, and inside your own exports.</p>
      <div class="flex gap-2">
        <button onclick="obGoto(2)" class="btn2 flex-1">Back</button>
        <button onclick="finishOnboarding(false)" class="btn2 flex-1">Skip</button>
        <button onclick="finishOnboarding(true)" class="btn flex-1">Create profile</button>
      </div>
    </div>

    <div id="ob-step-4" class="space-y-4 text-center hidden">
      <div class="text-5xl">✅</div>
      <h2 class="text-xl font-bold">You're all set, <span id="ob-hello"></span>!</h2>
      <p class="text-sm text-slate-400">Your data is isolated per profile and exportable anytime.</p>
      <button onclick="enterApp()" class="btn w-full">Enter the app</button>
    </div>

    <div class="pt-2 border-t border-slate-800 text-center">
      <button onclick="useDemo()" class="text-sm text-slate-400 hover:text-emerald-400 underline">Or explore with the synthetic Demo User (no account)</button>
    </div>
  </div>
</div>

<!-- ============ MAIN APP ============ -->
<div id="screen-app" class="hidden">
  <header class="sticky top-0 z-40 bg-slate-950/95 backdrop-blur border-b border-slate-800">
    <div class="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between gap-3">
      <div class="flex items-center gap-2.5">
        <div class="w-9 h-9 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-lg flex items-center justify-center font-black">P</div>
        <span class="font-black tracking-tight text-sm sm:text-base">PEPTIDE SAFETY TRACKER</span>
      </div>
      <button onclick="showStart()" class="text-xs bg-slate-800 border border-slate-700 px-3 py-1.5 rounded-full font-semibold hover:border-emerald-600" id="profile-chip"></button>
    </div>
    <!-- Demo boundary banner -->
    <div id="demo-banner" class="hidden bg-amber-950/60 border-t border-amber-800 px-4 py-2 flex items-center justify-between gap-3">
      <p class="text-xs sm:text-sm text-amber-100 font-semibold flex items-center gap-2"><span data-icon="flask" data-ico-size="16"></span>Demo mode — these are sample records, not your data.</p>
      <button onclick="resetDemo()" class="text-xs bg-amber-800 hover:bg-amber-700 text-white px-3 py-1.5 rounded-lg font-bold whitespace-nowrap">Reset demo data</button>
    </div>
  </header>

  <main class="max-w-3xl mx-auto p-4 md:p-6 space-y-6">
    <div class="bg-amber-950/30 border border-amber-900/60 p-3 rounded-xl text-xs text-amber-100 leading-relaxed"><strong>Disclaimer:</strong> <span id="disclaimer-text">This app is not medical advice; many research peptides are not FDA-approved.</span>
      <details class="mt-1"><summary class="text-amber-300 underline">Learn more</summary>
        <span id="disclaimer-more" class="block pt-1 text-amber-200/90">This app records what you enter, never recommends doses, and never rates brands as safe or unsafe. Many research peptides are not FDA-approved, and compounded copies carry FDA-documented risks. Verify anything important with official sources and a licensed clinician.</span>
      </details>
    </div>

    <!-- TODAY -->
    <section id="sec-today" class="space-y-6">
      <div class="card p-6">
        <h1 class="text-2xl font-black">Today <span id="today-date" class="text-sm font-semibold text-slate-400"></span></h1>
        <p id="dash-sub" class="text-sm text-slate-400 mt-1"></p>
        <p class="text-xs text-slate-500">Use the <strong>+</strong> button below to log a dose, a symptom, or an observation.</p>
      </div>
      <div class="grid grid-cols-3 gap-3 text-center">
        <div class="card p-4"><span class="text-xs text-slate-400 block">Entries</span><span id="stat-usage" class="text-2xl font-black text-emerald-400">0</span></div>
        <div class="card p-4"><span class="text-xs text-slate-400 block">Reminders</span><span id="stat-reminders" class="text-2xl font-black text-sky-400">0</span></div>
        <div class="card p-4"><span class="text-xs text-slate-400 block">Symptoms</span><span id="stat-symptoms" class="text-2xl font-black text-amber-400">0</span></div>
      </div>
      <div class="card p-5 space-y-2">
        <h2 class="font-bold">Due today (from your reminders)</h2>
        <p class="text-xs text-slate-400">Reminders are <strong>in-app only</strong> — they appear in this list while the app is open in a browser tab. <details class="inline"><summary class="inline text-slate-500 underline">Learn more</summary><span class="block pt-1 text-slate-500">Nothing is delivered when the app is closed; this is not a phone alarm. A due reminder without an entry is <strong>"not logged"</strong>, never "missed" — and the app gives no catch-up instructions.</span></details></p>
        <div id="due-today" class="divide-y divide-slate-800"></div>
      </div>
      <div class="card p-5 space-y-2">
        <h2 class="font-bold">Logged today</h2>
        <div id="logged-today" class="divide-y divide-slate-800"></div>
      </div>
      <div class="card p-5 space-y-2">
        <h2 class="font-bold">Recent observations <span class="text-xs text-slate-400 font-normal">(no dose attached)</span></h2>
        <div id="observation-list" class="divide-y divide-slate-800"></div>
      </div>
    </section>

    <!-- HISTORY -->
    <section id="sec-history" class="hidden space-y-6">
      <div class="card p-5 space-y-3">
        <h2 class="text-lg font-bold">Filter history</h2>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div>
            <label class="block text-xs text-slate-400 mb-1">Product</label>
            <input id="f-product" oninput="renderHistory()" placeholder="e.g., BPC-157" class="inp">
          </div>
          <div>
            <label class="block text-xs text-slate-400 mb-1">From date</label>
            <input id="f-from" type="date" onchange="renderHistory()" class="inp">
          </div>
          <div>
            <label class="block text-xs text-slate-400 mb-1">To date</label>
            <input id="f-to" type="date" onchange="renderHistory()" class="inp">
          </div>
          <div>
            <label class="block text-xs text-slate-400 mb-1">Event type</label>
            <select id="f-type" onchange="renderHistory()" class="inp">
              <option value="all">All events</option>
              <option value="usage">Administrations</option>
              <option value="observation">Observations</option>
              <option value="symptom">Symptoms</option>
            </select>
          </div>
        </div>
        <div class="flex flex-wrap gap-2 items-center">
          <button onclick="clearHistFilters()" class="btn2 text-xs">Clear filters</button>
          <button onclick="openVisitSummary()" class="btn2 text-xs"><span class="inline-flex items-center gap-1"><span data-icon="note" data-ico-size="14"></span>Printable visit summary (uses these filters)</span></button>
          <span id="f-status" class="text-xs text-slate-500"></span>
        </div>
        <p class="text-xs text-slate-500">The product filter applies to administrations and symptoms; observations carry no product, so they stay listed.</p>
      </div>
      <div class="card p-5 space-y-2" id="usage-history-card">
        <h2 class="text-lg font-bold">Usage history</h2>
        <p class="text-xs text-slate-400">Tap an entry for the full timestamp, notes, and any corrections.</p>
        <div id="usage-list" class="divide-y divide-slate-800"></div>
      </div>
      <div class="card p-5 space-y-2" id="symptom-history-card">
        <h2 class="text-lg font-bold">Symptom history</h2>
        <div id="symptom-list" class="divide-y divide-slate-800"></div>
      </div>
      <div class="card p-5 space-y-2" id="observation-history-card">
        <h2 class="text-lg font-bold">Observation history <span class="text-xs text-slate-400 font-normal">(measurements with no administration event)</span></h2>
        <div id="observation-history" class="divide-y divide-slate-800"></div>
      </div>
      <div class="card p-5 space-y-3">
        <h2 class="text-lg font-bold">Reminders <span class="text-xs text-slate-400 font-normal">(you configure them — the app never suggests schedules or amounts)</span></h2>
        <p class="text-xs text-amber-200 bg-amber-950/40 border border-amber-900/60 rounded-lg px-3 py-2 leading-relaxed">Honest delivery status: reminders are <strong>display-only and in-app</strong> — they do <strong>not</strong> deliver when the app is closed, in the background, or on the lock screen; use your phone's alarm for anything time-critical.</p>
        <details class="text-xs text-amber-200/80"><summary class="underline">Learn more</summary>
          <p class="pt-1">Reminders show up in this list and on Today while this app is open in a browser tab. Pausing or deleting a reminder immediately removes it from the due list (there is no background scheduler that could keep firing).</p>
        </details>
        <form onsubmit="addReminder(event)" class="grid grid-cols-2 gap-3" novalidate>
          <div>
            <label class="block text-xs text-slate-400 mb-1">Product / peptide</label>
            <div class="picker-wrap">
              <input id="r-name" required placeholder="Type to search…" autocomplete="off" class="inp">
              <div id="r-name-dd" class="picker-list hidden"></div>
            </div>
          </div>
          <div>
            <label class="block text-xs text-slate-400 mb-1">Time (device local time)</label>
            <input id="r-time" required type="time" class="inp">
          </div>
          <div class="col-span-2">
            <label class="block text-xs text-slate-400 mb-1">Days</label>
            <div id="r-days-chips" class="flex flex-wrap gap-2"></div>
            <input type="hidden" id="r-days">
            <p class="text-xs text-slate-500 mt-1">Reminder times stay as wall-clock HH:MM in your device's local time — if DST shifts, the app keeps showing the same local time.</p>
          </div>
          <div class="flex items-end">
            <button class="btn w-full" id="r-submit"><span class="flex items-center justify-center gap-2"><span data-icon="plus" data-ico-size="16"></span>Add</span></button>
          </div>
          <div class="err col-span-2" id="r-error"></div>
        </form>
        <div class="flex flex-wrap items-center gap-2 pt-1">
          <button onclick="testNotification()" class="btn2 text-xs">Send test notification</button>
          <span id="notif-status" class="text-xs text-slate-400"></span>
        </div>
        <div id="reminder-list" class="divide-y divide-slate-800"></div>
      </div>
    </section>

    <!-- LEARN -->
    <section id="sec-learn" class="hidden space-y-6">
      <div class="card p-5 space-y-2 border-l-4 !border-l-rose-500">
        <h2 class="text-lg font-bold text-rose-300 flex items-center gap-2"><span data-icon="warn" data-ico-size="20"></span>When to get help</h2>
        <p class="text-sm text-slate-300 leading-relaxed">If you ever experience severe symptoms — trouble breathing, swelling of face/throat, chest pain, fainting, or rapidly worsening reactions — <strong>seek emergency medical care immediately</strong> and tell clinicians exactly what you took (your export file is designed to be shown to them). For anything milder but persistent, log it and raise it with a licensed healthcare provider.</p>
      </div>

      <div class="card p-5 space-y-2">
        <h2 class="text-lg font-bold text-emerald-300 flex items-center gap-2"><span data-icon="note" data-ico-size="20"></span>Growth hormone & height claims</h2>
        <p class="text-sm text-slate-300 leading-relaxed"><strong>Educational note — not advice.</strong> "Growth hormone is not a general height enhancer. Once growth plates have fused, HGH does not increase height. This app cannot assess growth potential or recommend hormone treatment. Discuss growth concerns with a qualified clinician." (Cleveland Clinic — <a class="text-emerald-400 underline" href="https://my.clevelandclinic.org/health/articles/23309-human-growth-hormone-hgh" target="_blank" rel="noopener">Human Growth Hormone (HGH)</a>.) The same reference lists health risks of synthetic HGH, including swelling, joint/muscle pain, and insulin resistance. MedlinePlus identifies somatropin as a human growth hormone analog used for specific growth-hormone-related and other medical conditions — not a general height or appearance enhancer (<a class="text-emerald-400 underline" href="https://medlineplus.gov/druginfo/meds/a622022.html" target="_blank" rel="noopener">MedlinePlus: somatropin injection</a>). FDA-approved somatropin products exist for specific labeled indications in specific products only; using growth hormone or growth-hormone secretagogues (which have no FDA-approved human products) for "height enhancement" is not FDA-approved (<a class="text-emerald-400 underline" href="https://www.fda.gov/drugs/human-drug-compounding" target="_blank" rel="noopener">FDA compounding</a>). This app never estimates growth-plate status or growth potential from your age, height, photos, or any other data. The Height tracking goal is a plain journal measurement only — bring your export to a licensed clinician instead of expecting answers here.</p>
      </div>

      <div class="card p-5 space-y-2">
        <h2 class="text-lg font-bold text-emerald-300 flex items-center gap-2"><span data-icon="book" data-ico-size="20"></span>What "regulatory status" means</h2>
        <ul class="text-sm text-slate-300 space-y-2 list-disc pl-5 leading-relaxed">
          <li><strong>"Approved products exist"</strong> is an ingredient-level statement: FDA-approved prescription products exist for this ingredient, but approval applies only to those <em>specific products</em>. Other versions — including compounded and "research" versions of the same molecule — are <strong>not</strong> approved. FDA has specifically warned about unapproved GLP-1 drugs (<a class="text-emerald-400 underline" href="https://www.fda.gov/drugs/drug-alerts-and-statements/fdas-concerns-unapproved-glp-1-drugs-used-weight-loss" target="_blank" rel="noopener">fda.gov</a>).</li>
          <li><strong>"No FDA-approved product"</strong> means no FDA-approved human use exists for that ingredient at all.</li>
          <li><strong>"FDA compounding context"</strong> means FDA has published risk discussion; read it directly at the <a class="text-emerald-400 underline" href="https://www.fda.gov/drugs/human-drug-compounding" target="_blank" rel="noopener">compounding page</a>.</li>
          <li>Approval is checked per <strong>exact product</strong> in <a class="text-emerald-400 underline" href="https://www.accessdata.fda.gov/scripts/cder/daf/" target="_blank" rel="noopener">Drugs@FDA</a> — never per ingredient; use <a class="text-emerald-400 underline" href="https://dailymed.nlm.nih.gov/" target="_blank" rel="noopener">DailyMed</a> for labeling. A DailyMed listing does not by itself establish FDA approval: DailyMed also includes labeling for products that are not FDA-approved.</li>
        </ul>
      </div>

      <div class="card p-5 space-y-2">
        <h2 class="text-lg font-bold text-emerald-300 flex items-center gap-2"><span data-icon="store" data-ico-size="20"></span>Sourcing & pharmacies</h2>
        <p class="text-sm text-slate-300 leading-relaxed">FDA's <a class="text-emerald-400 underline" href="https://www.fda.gov/consumers/buying-medicine-online" target="_blank" rel="noopener">Buying Medicine Online</a> guidance: use state-licensed pharmacies, expect a valid prescription for prescription drugs, and be wary of sites selling "research use only" chemicals for human consumption — FDA explicitly warns these are not for human use. The brand directory here deliberately <strong>never rates any seller</strong>; use the checklist below to do your own checks.</p>
      </div>

      <div class="card p-5 space-y-2">
        <h2 class="text-lg font-bold text-emerald-300 flex items-center gap-2"><span data-icon="note" data-ico-size="20"></span>Getting the most from your log</h2>
        <ul class="text-sm text-slate-300 space-y-2 list-disc pl-5 leading-relaxed">
          <li>Record every entry with an <strong>explicit unit</strong> (mcg, mg, IU, units, mL) — mixed units are the most common source of confusion.</li>
          <li>Log symptoms the same day with severity. Patterns in your symptom log are information for <strong>your clinician</strong>, not a diagnosis.</li>
          <li>Before any medical appointment, use <strong>Settings → Export</strong> and bring the file.</li>
        </ul>
      </div>

      <div class="card p-5 space-y-2">
        <h2 class="text-lg font-bold text-emerald-300 flex items-center gap-2"><span data-icon="chat" data-ico-size="20"></span>Questions to ask a licensed clinician</h2>
        <ul class="text-sm text-slate-300 space-y-2 list-disc pl-5 leading-relaxed">
          <li>Is this substance FDA-approved for my situation, and what are the labeled risks?</li>
          <li>What monitoring (labs, check-ups) makes sense while I use anything off-label?</li>
          <li>Could this interact with my current medications or conditions?</li>
          <li>Where can I get a legitimate prescription instead of an unverified source?</li>
        </ul>
        <p class="text-xs text-slate-400">This app can't answer these — a licensed professional can.</p>
      </div>

      <div class="card p-5 space-y-3">
        <h2 class="text-lg font-bold text-emerald-300 flex items-center gap-2"><span data-icon="lock" data-ico-size="20"></span>Your privacy</h2>
        <p class="text-sm text-slate-300 leading-relaxed">All entries live in a local SQLite file on this machine. No network calls carry your data — the only external links are ones <strong>you</strong> click. Review the <a class="text-emerald-400 underline" href="https://www.hhs.gov/hipaa/for-professionals/privacy/special-topics/health-apps/index.html" target="_blank" rel="noopener">HHS health-app privacy guidance</a> before ever syncing or sharing health data.</p>
      </div>

      <div class="card p-5 space-y-4" id="reference-card">
        <h2 class="text-lg font-bold">Peptides & related medications <span class="text-xs text-slate-400 font-normal">— sourced reference information (MedlinePlus / FDA / DailyMed; regulatory status only, no recommendations)</span></h2>
        <p class="text-xs text-slate-400">"Source checked" means the entry's statement was verified against the cited official page on the date shown — source verification only, <strong>not qualified clinical review</strong>, never implying safety or endorsement.</p>
        <details class="text-xs"><summary class="text-emerald-400 underline">Learn more</summary>
          <p class="text-slate-400 pt-1">Source verification is done by this app's developer against the cited official page on the date shown. It is not qualified clinical review. It never implies safety, approval of your use, or endorsement of any product or brand.</p>
        </details>
        <input id="cat-search" oninput="renderCatalog()" placeholder="Search — including aliases like “HGH”…" class="inp">
        <div id="hgh-search-note" class="hidden text-xs text-amber-200 bg-amber-950/40 border border-amber-900/60 rounded-lg px-3 py-2 leading-relaxed"></div>
        <div id="catalog-list" class="space-y-2"></div>
      </div>

      <div class="card p-5 space-y-3">
        <h2 class="text-lg font-bold">Verify a product <span class="text-xs text-slate-400 font-normal">— the app checks nothing for you; it builds official links and tracks when you marked each item checked</span></h2>
        <div class="flex gap-2">
          <input id="v-name" placeholder="Product or ingredient name" class="inp flex-1">
          <button onclick="verify()" class="btn">Start checklist</button>
        </div>
        <div id="verify-result" class="space-y-2"></div>
      </div>

      <div class="card p-5 space-y-2">
        <h2 class="text-lg font-bold">Brand directory <span class="text-xs text-slate-400 font-normal">— neutral, never rated or endorsed</span></h2>
        <div id="brand-list" class="divide-y divide-slate-800"></div>
      </div>
    </section>

    <!-- SETTINGS -->
    <section id="sec-settings" class="hidden space-y-6">
      <div class="card p-5 space-y-3">
        <h2 class="text-lg font-bold">My profile</h2>
        <div><label class="block text-sm text-slate-400 mb-1">Age</label>
          <input id="set-age" type="number" min="1" max="120" class="inp" placeholder="not set"></div>
        <div><label class="block text-sm text-slate-400 mb-1">What I'm tracking</label>
          <input id="set-note" class="inp" placeholder="not set"></div>
        <button onclick="saveProfile()" class="btn">Save profile</button>
      </div>
      <div class="card p-5 space-y-3">
        <h2 class="text-lg font-bold">Export</h2>
        <p class="text-sm text-slate-400">Exports contain <strong>only this profile's</strong> data: usage, symptoms, observations and reminders. Nothing leaves your machine unless you share the file yourself.</p>
        <div class="flex flex-wrap gap-2">
          <button onclick="exportData('json')" class="btn"><span class="flex items-center justify-center gap-2"><span data-icon="download" data-ico-size="16"></span>Export JSON</span></button>
          <button onclick="exportData('csv')" class="btn2"><span class="flex items-center justify-center gap-2"><span data-icon="download" data-ico-size="16"></span>Export CSV</span></button>
        </div>
      </div>
      <div class="card p-5 space-y-2">
        <h2 class="text-lg font-bold">Privacy model <span class="text-xs text-slate-400 font-normal">(matches the actual architecture — a single-device local app)</span></h2>
        <p class="text-sm text-slate-300 leading-relaxed">All records stay in a local database on this device — nothing is transmitted automatically, and anyone who can use this device can open any profile.</p>
        <details class="text-sm"><summary class="text-emerald-400 underline">Learn more</summary>
          <ul class="text-slate-300 space-y-2 list-disc pl-5 pt-2">
            <li><strong>Architecture:</strong> this is a single-device local app — a small server process on this machine serving a browser page, with records in a local SQLite file (<code class="text-emerald-400">peptide_safety.db</code>). It is not a hosted multi-user service.</li>
            <li><strong>Profile separation is not authentication.</strong> Profiles organize records, but <em>anyone who can use this device can open any profile</em>. There are no passwords. Do not store records here that must stay private from other people who use this device. A real hosted multi-user version would require authentication, server-side ownership checks, and review before accepting real health records.</li>
            <li><strong>What leaves the machine:</strong> nothing automatically. No analytics, no external AI, no third-party transmission. The only network requests are the page loading from this machine and official-source links <strong>you</strong> click (no personal data is in those links).</li>
            <li><strong>Back up and restore:</strong> use Settings → Export to save a copy of this profile's data (JSON). Restoring means keeping the exported file safe — there is no cloud backup, and deleted records cannot be recovered from the app.</li>
            <li><strong>Deletion:</strong> deleting an entry or a profile removes those rows from the local database permanently.</li>
            <li>Tracking goals and their journal values are per-profile, stay on this device, and appear only in your own exports — never in any outbound link.</li>
            <li>Handling real health data on shared devices? Review the <a class="text-emerald-400 underline" href="https://www.hhs.gov/hipaa/for-professionals/privacy/special-topics/health-apps/index.html" target="_blank" rel="noopener">HHS health-app guidance</a>, and complete a privacy/security review before real records.</li>
          </ul>
        </details>
      </div>
      <div class="card p-5 space-y-3">
        <h2 class="text-lg font-bold">Tracking goals <span class="text-xs text-slate-400 font-normal">(optional — personalize your journal)</span></h2>
        <p class="text-sm text-slate-300 leading-relaxed" id="goals-explanation">Your goals customize your journal, not medication recommendations. Recording a goal does not mean a product is effective or appropriate for it.</p>
        <p class="text-xs text-slate-500">These are personal journal fields, not clinical indications — nothing here says what a substance treats, causes, or should be used for. Selecting none is fine; changes never delete or alter existing entries.</p>
        <div id="goal-chips" class="flex flex-wrap gap-2"></div>
        <div id="custom-goal-text" class="hidden">
          <label class="block text-xs text-slate-400 mb-1">Your custom reason (private — your own words)</label>
          <input id="goal-custom-input" maxlength="200" class="inp" placeholder="e.g., keeping a neutral record">
        </div>
        <div id="height-goal-note" class="hidden text-xs text-amber-200 bg-amber-950/40 border border-amber-900/60 rounded-lg px-3 py-2 leading-relaxed"></div>
        <button onclick="saveGoals()" class="btn">Save goals</button>
        <p class="text-xs text-slate-500">Goals and their journal values are stored per profile, stay on this device, and are included only in your own exports.</p>
      </div>
      <div class="card p-5 space-y-2">
        <h2 class="text-lg font-bold">My saved products</h2>
        <p class="text-xs text-slate-400">Quick-pick entries for the log sheet. Saved per profile, with optional default unit.</p>
        <div id="settings-products" class="divide-y divide-slate-800"></div>
      </div>
      <div class="card p-5 space-y-2">
        <h2 class="text-lg font-bold">Profiles on this device</h2>
        <div id="profiles-list" class="divide-y divide-slate-800"></div>
        <button onclick="showStart()" class="btn2 w-full mt-2"><span class="flex items-center justify-center gap-2"><span data-icon="plus" data-ico-size="16"></span>New profile</span></button>
      </div>
    </section>
  </main>

  <!-- BOTTOM NAV -->
  <nav class="bottomnav">
    <div class="max-w-3xl mx-auto flex items-end">
      <button class="navbtn active" data-tab="today" onclick="switchTab('today')"><span class="navico" data-icon="home"></span>Today</button>
      <button class="navbtn" data-tab="history" onclick="switchTab('history')"><span class="navico" data-icon="clock"></span>History</button>
      <div class="flex-1 flex justify-center"><button class="fab" onclick="openFabChooser()" title="Log something" aria-label="Log something"><span data-icon="plus" data-ico-size="28"></span></button></div>
      <button class="navbtn" data-tab="learn" onclick="switchTab('learn')"><span class="navico" data-icon="book"></span>Learn</button>
      <button class="navbtn" data-tab="settings" onclick="switchTab('settings')"><span class="navico" data-icon="gear"></span>Settings</button>
    </div>
  </nav>

  <!-- FAB CHOOSER: one entry point for all logging (A.2) -->
  <div id="fab-chooser" class="hidden fixed inset-0 bg-black/80 z-[60] flex items-end sm:items-center justify-center p-0 sm:p-4" onclick="if(event.target===this)closeFabChooser()">
    <div class="bg-slate-900 border border-slate-800 w-full sm:max-w-sm rounded-t-2xl sm:rounded-2xl p-5 space-y-2">
      <p class="text-xs text-slate-400 text-center pb-1">What are you logging?</p>
      <button onclick="closeFabChooser();openLogSheet()" class="btn w-full !py-3.5"><span class="flex items-center justify-center gap-2"><span data-icon="plus" data-ico-size="18"></span>A dose (administration)</span></button>
      <button onclick="closeFabChooser();openObservationSheet()" class="btn2 w-full !py-3.5"><span class="flex items-center justify-center gap-2"><span data-icon="note" data-ico-size="18" class="text-sky-400"></span>An observation (no dose)</span></button>
      <button onclick="closeFabChooser();openSymptomSheet()" class="btn2 w-full !py-3.5"><span class="flex items-center justify-center gap-2"><span data-icon="warn" data-ico-size="18" class="text-amber-400"></span>A symptom</span></button>
      <button onclick="closeFabChooser()" class="w-full text-center text-xs text-slate-400 py-2 underline">Cancel</button>
    </div>
  </div>

  <!-- LOG USE SHEET -->
  <div id="log-sheet" class="hidden fixed inset-0 bg-black/80 z-[60] flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-slate-900 border border-slate-800 w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-6 space-y-4">
      <div class="flex justify-between items-center"><h3 class="font-bold text-lg flex items-center gap-2"><span data-icon="plus" data-ico-size="20" class="text-emerald-400"></span><span id="log-sheet-title">Log use</span></h3><button onclick="closeLogSheet()" class="text-slate-400 text-xl" aria-label="Close"><span data-icon="close" data-ico-size="20"></span></button></div>
      <div id="product-chips" class="flex flex-wrap gap-2"></div>
      <form onsubmit="logUsage(event)" class="space-y-3" novalidate>
        <div>
          <label class="block text-xs text-slate-400 mb-1">Product / peptide name</label>
          <div class="picker-wrap">
            <input id="u-name" required placeholder="Type to search or add…" autocomplete="off" class="inp">
            <div id="u-name-dd" class="picker-list hidden"></div>
          </div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-slate-400 mb-1">Amount (your own entry)</label>
            <input id="u-amount" required type="number" step="any" min="0.000001" placeholder="e.g., 250" class="inp">
          </div>
          <div>
            <label class="block text-xs text-slate-400 mb-1">Unit</label>
            <select id="u-unit" class="inp"><option>mcg</option><option>mg</option><option>IU</option><option>units</option><option>mL</option></select>
          </div>
        </div>
        <div>
          <label class="block text-xs text-slate-400 mb-1">When</label>
          <input id="u-when" type="datetime-local" class="inp">
        </div>
        <div>
          <label class="block text-xs text-slate-400 mb-1">Notes (optional)</label>
          <input id="u-notes" placeholder="Anything worth remembering" class="inp">
        </div>
        <label id="u-save-product-row" class="flex items-center gap-3 text-sm cursor-pointer">
          <input type="checkbox" id="u-save-product" class="w-4 h-4 accent-emerald-500">
          <span class="flex items-center gap-1.5 text-slate-300"><span data-icon="star" data-ico-size="16" class="text-amber-400"></span>Save this product to my list</span>
        </label>
        <div class="err" id="u-error"></div>
        <button class="btn w-full !py-3" id="u-submit"><span class="flex items-center justify-center gap-2"><span data-icon="check" data-ico-size="18"></span><span id="u-submit-label">Save entry</span></span></button>
      </form>
    </div>
  </div>

  <!-- LOG OBSERVATION SHEET (no administration event) -->
  <div id="observation-sheet" class="hidden fixed inset-0 bg-black/80 z-[60] flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-slate-900 border border-slate-800 w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-6 space-y-4">
      <div class="flex justify-between items-center"><h3 class="font-bold text-lg flex items-center gap-2"><span data-icon="note" data-ico-size="20" class="text-sky-400"></span><span id="o-sheet-title">Log an observation</span></h3><button onclick="closeObservationSheet()" class="text-slate-400 text-xl" aria-label="Close"><span data-icon="close" data-ico-size="20"></span></button></div>
      <p class="text-xs text-slate-400">Records a personal measurement (sleep, height, weight, etc.) <strong>on its own</strong> — this creates no dose entry and attaches to no administration event.</p>
      <form onsubmit="logObservation(event)" class="space-y-3" novalidate>
        <div>
          <label class="block text-xs text-slate-400 mb-1">When</label>
          <input id="o-when" type="datetime-local" class="inp">
        </div>
        <div id="observation-fields" class="space-y-3"></div>
        <div>
          <label class="block text-xs text-slate-400 mb-1">Notes (optional)</label>
          <input id="o-notes" placeholder="Anything worth remembering" class="inp">
        </div>
        <div class="err" id="o-error"></div>
        <button class="btn w-full !py-3" id="o-submit"><span class="flex items-center justify-center gap-2"><span data-icon="check" data-ico-size="18"></span><span id="o-submit-label">Save observation</span></span></button>
      </form>
    </div>
  </div>

  <!-- LOG SYMPTOM SHEET -->
  <div id="symptom-sheet" class="hidden fixed inset-0 bg-black/80 z-[60] flex items-end sm:items-center justify-center p-0 sm:p-4">
    <div class="bg-slate-900 border border-slate-800 w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-6 space-y-4">
      <div class="flex justify-between items-center"><h3 class="font-bold text-lg flex items-center gap-2"><span data-icon="warn" data-ico-size="20" class="text-amber-400"></span>Log a symptom</h3><button onclick="closeSymptomSheet()" class="text-slate-400 text-xl" aria-label="Close"><span data-icon="close" data-ico-size="20"></span></button></div>
      <form onsubmit="logSymptom(event)" class="space-y-3" novalidate>
        <div>
          <label class="block text-xs text-slate-400 mb-1">Product / peptide name</label>
          <div class="picker-wrap">
            <input id="s-name" required placeholder="Type to search…" autocomplete="off" class="inp">
            <div id="s-name-dd" class="picker-list hidden"></div>
          </div>
        </div>
        <div>
          <label class="block text-xs text-slate-400 mb-1">Severity</label>
          <select id="s-severity" class="inp">
            <option value="1">1 — very mild</option><option value="2">2 — mild</option>
            <option value="3" selected>3 — moderate</option><option value="4">4 — severe</option>
            <option value="5">5 — very severe</option>
          </select>
        </div>
        <div>
          <label class="block text-xs text-slate-400 mb-1">What did you feel?</label>
          <textarea id="s-desc" required placeholder="Describe the symptom" class="inp h-20"></textarea>
        </div>
        <div class="err" id="s-error"></div>
        <button class="btn w-full !py-3" id="s-submit"><span class="flex items-center justify-center gap-2"><span data-icon="check" data-ico-size="18"></span>Save symptom</span></button>
      </form>
    </div>
  </div>
</div>

<script>
let users = [], catalog = [], lastUsage = [], lastSymptoms = [], lastReminders = [], lastObservations = [], savedProducts = [], myGoals = [], goalRegistry = {};
const DISCLAIMER = "__DISCLAIMER__";
document.getElementById('disclaimer-more').innerText = DISCLAIMER;

async function jget(url){ const r = await fetch(url); if(!r.ok){ throw new Error(await r.text()); } return r.json(); }
function esc(s){ const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }
function fmtDate(iso){
  const d = new Date(iso); if(isNaN(d)) return esc(iso);
  return d.toLocaleDateString(undefined,{month:'short',day:'numeric'}) + ', ' +
         d.toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'});
}

/* ---------------- SVG icon system ---------------- */
const ICONS = {
  home:   '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M10 21v-6h4v6"/>',
  clock:  '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
  book:   '<path d="M4 5a2 2 0 0 1 2-2h13v18H6a2 2 0 0 1-2-2z"/><path d="M8 3v18"/>',
  gear:   '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3h.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5h.1a1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9v.1a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  plus:   '<path d="M12 5v14M5 12h14"/>',
  close:  '<path d="M6 6l12 12M18 6L6 18"/>',
  trash:  '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  star:   '<path d="m12 3 2.7 5.8 6.3.7-4.7 4.3 1.3 6.2L12 17l-5.6 3 1.3-6.2L3 9.5l6.3-.7z"/>',
  check:  '<path d="m4 12.5 5 5L20 6.5"/>',
  warn:   '<path d="M12 3 2.5 20h19z"/><path d="M12 9.5V14M12 17h.01"/>',
  download:'<path d="M12 3v12M6.5 10.5 12 16l5.5-5.5"/><path d="M4 20h16"/>',
  lock:   '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  chat:   '<path d="M21 12a8 8 0 1 0-3.5 6.6L21 20z"/>',
  store:  '<path d="M4 9 5.5 4h13L20 9"/><path d="M4 9a2.5 2.5 0 0 0 5 0 2.5 2.5 0 0 0 5 0 2.5 2.5 0 0 0 5 0"/><path d="M5 12v8h14v-8M9 20v-5h6v5"/>',
  note:   '<path d="M5 3h14v18H5z"/><path d="M9 8h6M9 12h6M9 16h4"/>',
  shield: '<path d="M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6z"/>',
  flask:  '<path d="M9 3h6M10 3v5l-5.5 9.5A2 2 0 0 0 6.2 21h11.6a2 2 0 0 0 1.7-3.5L14 8V3"/><path d="M7.5 15h9"/>'
};
function icon(name, size=20, cls=''){
  return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="'+size+'" height="'+size+'" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="'+cls+'" aria-hidden="true">'+(ICONS[name]||'')+'</svg>';
}
function renderIcons(){
  document.querySelectorAll('[data-icon]').forEach(el => {
    el.innerHTML = icon(el.dataset.icon, parseInt(el.dataset.icoSize||'20',10), el.className);
  });
}

/* ---------------- toast + validation helpers ---------------- */
let toastTimer = null;
function toast(msg, isErr=false, action=null){
  const t = document.getElementById('toast');
  t.innerHTML = icon(isErr ? 'warn' : 'check', 16) + '<span>'+esc(msg)+'</span>'
    + (action ? ' <button class="underline font-bold ml-1" id="toast-action">'+esc(action.label)+'</button>' : '');
  if(action) document.getElementById('toast-action').onclick = action.run;
  t.classList.toggle('err', isErr);
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), action ? 6000 : 2600);
}
function formError(errId, msg, inputEl){
  const box = document.getElementById(errId);
  box.innerText = msg || '';
  box.classList.toggle('show', !!msg);
  if(inputEl) inputEl.classList.add('invalid');
}
function clearErrors(formEl){
  formEl.querySelectorAll('.err').forEach(e => { e.classList.remove('show'); e.innerText=''; });
  formEl.querySelectorAll('.invalid').forEach(e => e.classList.remove('invalid'));
}
function localDT(d=new Date()){
  const p = n => String(n).padStart(2,'0');
  return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+'T'+p(d.getHours())+':'+p(d.getMinutes());
}

/* ---------------- reusable searchable product picker ---------------- */
function attachPicker(inputId, ddId, onPick){
  const input = document.getElementById(inputId);
  const dd = document.getElementById(ddId);
  let items = [];
  const close = () => dd.classList.add('hidden');

  function suggestions(q){
    const ql = q.toLowerCase();
    const seen = new Set(), out = [];
    const add = (name, src, product, force) => {
      const k = name.toLowerCase();
      if(seen.has(k) || (ql && !k.includes(ql) && !force)) return;
      seen.add(k); out.push({name, src, product});
    };
    (savedProducts||[]).forEach(p => add(p.name, 'saved', p));
    (lastUsage||[]).forEach(u => add(u.peptide_name, 'recent', null));
    (lastSymptoms||[]).forEach(s => add(s.peptide_name, 'recent', null));
    (catalog||[]).forEach(c => {
      const nameHit = !ql || c.name.toLowerCase().includes(ql);
      const aliasHit = ql && (c.aliases||[]).some(a => a.toLowerCase().includes(ql));
      // alias matches surface the canonical name and explain the link
      add(c.name, 'reference', null, nameHit || aliasHit);
    });
    if(ql && !seen.has(ql)) out.push({name: q, src: 'new', product: null});
    return out.slice(0, 12);
  }

  function render(){
    items = suggestions(input.value.trim());
    dd.innerHTML = items.length ? items.map((it, i) => `
      <div class="dd-item" data-i="${i}">
        <span class="font-semibold">${esc(it.name)}</span>
        <span class="src">${it.src}</span>
      </div>`).join('') : '';
    dd.classList.toggle('hidden', items.length === 0);
    dd.querySelectorAll('.dd-item').forEach(el =>
      el.addEventListener('mousedown', ev => {
        ev.preventDefault();
        pick(items[parseInt(el.dataset.i,10)]);
      }));
  }

  function pick(it){
    input.value = it.name;
    input.classList.remove('invalid');
    if(onPick) onPick(it);
    close();
  }

  input.addEventListener('focus', render);
  input.addEventListener('input', render);
  input.addEventListener('blur', () => setTimeout(close, 120));
  // click outside any picker closes every open list (A.5)
  document.addEventListener('click', ev => {
    if(!ev.target.closest || !ev.target.closest('.picker-wrap')) close();
  });
  input.addEventListener('keydown', ev => {
    if(ev.key === 'Escape') close();
    if(ev.key === 'Enter' && !dd.classList.contains('hidden') && items.length){
      const first = items.find(it => it.name.toLowerCase() === input.value.trim().toLowerCase()) || items[0];
      ev.preventDefault(); pick(first);
    }
  });
}

/* ---------------- onboarding ---------------- */
document.getElementById('ob-consent').addEventListener('change', e => {
  document.getElementById('ob-next-1').disabled = !e.target.checked;
});
document.getElementById('ob-name').addEventListener('input', e => {
  document.getElementById('ob-next-2').disabled = e.target.value.trim().length === 0;
});

let obGoalKeys = [];
function obGoto(step){
  [1,2,3,4].forEach(i => document.getElementById('ob-step-'+i).classList.toggle('hidden', i !== step));
  [1,2,3,4].forEach(i => document.getElementById('dot-'+i).className =
    'h-1.5 flex-1 rounded-full ' + (i <= step ? 'bg-emerald-500' : 'bg-slate-700'));
  if(step === 3) renderObGoalChips();
}

// Optional goal selection (spec: "What would you like to track?" — chips with
// Skip). Same stable keys as the Settings editor; nothing here selects a
// peptide, pre-fills an amount, or promises an effect.
async function renderObGoalChips(){
  if(!goalRegistry || !Object.keys(goalRegistry).length){
    goalRegistry = (await jget('/api/goals/registry')).goals;
  }
  const {shown, hidden} = visibleGoalKeys(obGoalKeys, moreObGoalsOpen);
  const box = document.getElementById('ob-goal-chips');
  box.innerHTML = shown.map(key => `
    <button type="button" class="chip ${obGoalKeys.includes(key) ? '!border-emerald-500 !bg-emerald-950' : ''}"
      onclick="toggleObGoal('${key}')">${obGoalKeys.includes(key) ? '✓ ' : ''}${esc(goalRegistry[key].label)}</button>`).join('')
    + (hidden
        ? `<button type="button" class="chip !border-slate-500" onclick="moreObGoalsOpen=!moreObGoalsOpen;renderObGoalChips()">${moreObGoalsOpen ? '− Fewer goals' : '+ More goals (' + hidden + ')'}</button>`
        : '');
}

function toggleObGoal(key){
  obGoalKeys = obGoalKeys.includes(key) ? obGoalKeys.filter(k => k !== key) : [...obGoalKeys, key];
  renderObGoalChips();
}

async function finishOnboarding(withGoals){
  const body = {
    display_name: document.getElementById('ob-name').value.trim(),
    age: document.getElementById('ob-age').value || null,
    tracking_note: document.getElementById('ob-note').value,
    consent_ack: document.getElementById('ob-consent').checked
  };
  const r = await fetch('/api/users', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if(!r.ok){ alert((await r.json()).detail); obGoto(2); return; }
  const {user_id} = await r.json();
  localStorage.setItem('pst_user', user_id);
  if(withGoals && obGoalKeys.length){
    const gr = await fetch('/api/goals/' + user_id, {method:'PUT', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({goals: obGoalKeys})});
    if(!gr.ok){ toast('Profile created, but goals could not be saved — set them in Settings.', true); }
  }
  document.getElementById('ob-hello').innerText = body.display_name;
  obGoto(4);
}

function useDemo(){
  localStorage.setItem('pst_user', users.find(u => u.is_demo).id);
  enterApp();
}

async function showStart(){
  document.getElementById('screen-app').classList.add('hidden');
  document.getElementById('screen-start').classList.remove('hidden');
  obGoto(1);
  obGoalKeys = [];
  document.getElementById('ob-consent').checked = false;
  document.getElementById('ob-next-1').disabled = true;
  document.getElementById('ob-name').value = '';
  document.getElementById('ob-age').value = '';
  document.getElementById('ob-note').value = '';
  document.getElementById('ob-next-2').disabled = true;
}

async function enterApp(){
  await refreshUsers();
  document.getElementById('screen-start').classList.add('hidden');
  document.getElementById('screen-app').classList.remove('hidden');
  switchTab('today');
  await loadAll();
}

/* ---------------- tabs ---------------- */
function switchTab(tab){
  ['today','history','learn','settings'].forEach(t => {
    document.getElementById('sec-'+t).classList.toggle('hidden', t !== tab);
  });
  document.querySelectorAll('.navbtn').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === tab));
  window.scrollTo(0, 0);
}

/* ---------------- tracking goals (journal fields, not indications) ---------------- */
let goalCustomText = {};
async function loadGoals(){
  if(!goalRegistry || !Object.keys(goalRegistry).length){
    goalRegistry = (await jget('/api/goals/registry')).goals;
  }
  const d = (await jget('/api/goals/' + currentUID()));
  myGoals = d.goals;
  goalCustomText = {};
  (d.details || []).forEach(x => { if(x.custom_text) goalCustomText[x.goal_key] = x.custom_text; });
  renderGoalChips();
  // observations display friendly field labels, which need the registry
  if(lastObservations.length) renderObservations(lastObservations);
}

function goalFieldsOf(key){
  const g = goalRegistry[key] || {};
  const out = [];
  if(g.field) out.push(g.field);
  (g.fields || []).forEach(f => out.push(f));
  return out;
}

// label lookup: field key -> display label (searches every goal's fields)
function fieldLabel(fkey){
  for(const [k, g] of Object.entries(goalRegistry)){
    for(const f of goalFieldsOf(k)){
      if(f.key === fkey) return f.label;
    }
  }
  return fkey;
}

const COMMON_GOALS = ['sleep','bodyweight','energy','recovery','symptoms','appearance'];
let moreGoalsOpen = false, moreObGoalsOpen = false;

function goalChipOrder(){
  return ['sleep','recovery','energy','mood','appetite','digestion','joints','skin','libido','bodyweight','height','treatment','symptoms','appearance','growth_clinician','visit_prep','recordkeeping','custom'];
}

// Six common goals first; the rest stay behind a "More goals" toggle (A.6).
// Any goal the user has already selected always shows, so a selection is
// never hidden from view.
function visibleGoalKeys(selected, moreOpen){
  const keys = goalChipOrder().filter(k => goalRegistry[k]);
  if(moreOpen) return {shown: keys, hidden: 0};
  const shown = keys.filter(k => COMMON_GOALS.includes(k));
  keys.forEach(k => { if(!COMMON_GOALS.includes(k) && selected.includes(k)) shown.push(k); });
  return {shown, hidden: keys.length - shown.length};
}

function renderGoalChips(){
  const box = document.getElementById('goal-chips');
  const {shown, hidden} = visibleGoalKeys(myGoals, moreGoalsOpen);
  box.innerHTML = shown.map(key => {
    const g = goalRegistry[key];
    return `
    <button type="button" class="chip ${myGoals.includes(key) ? '!border-emerald-500 !bg-emerald-950' : ''}"
      onclick="toggleGoal('${key}')">${myGoals.includes(key) ? '✓ ' : ''}${esc(g.label)}</button>`;
  }).join('')
    + (hidden
        ? `<button type="button" class="chip !border-slate-500" onclick="moreGoalsOpen=!moreGoalsOpen;renderGoalChips()">${moreGoalsOpen ? '− Fewer goals' : '+ More goals (' + hidden + ')'}</button>`
        : '')
    + (myGoals.length ? '' : '<span class="text-xs text-slate-500">No goals selected — journal shows only the base fields.</span>');
  document.getElementById('custom-goal-text').classList.toggle('hidden', !myGoals.includes('custom'));
  if(myGoals.includes('custom') && !document.getElementById('goal-custom-input').value){
    document.getElementById('goal-custom-input').value = goalCustomText['custom'] || '';
  }
  const heightNote = document.getElementById('height-goal-note');
  const heightOn = myGoals.includes('height') || myGoals.includes('growth_clinician');
  heightNote.classList.toggle('hidden', !heightOn);
  if(heightOn){
    heightNote.innerHTML = '<strong>Growth hormone & height:</strong> "Growth hormone is not a general height enhancer. Once growth plates have fused, HGH does not increase height. This app cannot assess growth potential or recommend hormone treatment. Discuss growth concerns with a qualified clinician." (<a class="text-amber-100 underline" href="https://my.clevelandclinic.org/health/articles/23309-human-growth-hormone-hgh" target="_blank" rel="noopener">Cleveland Clinic</a>; risks include swelling, joint/muscle pain, and insulin resistance. This app never estimates growth-plate status or growth potential from your data.)';
  }
}

function toggleGoal(key){
  myGoals = myGoals.includes(key) ? myGoals.filter(k => k !== key) : [...myGoals, key];
  renderGoalChips();
}

async function saveGoals(){
  const customInput = document.getElementById('goal-custom-input');
  const custom_texts = {};
  if(myGoals.includes('custom') && customInput.value.trim()) custom_texts['custom'] = customInput.value.trim();
  const r = await fetch('/api/goals/' + currentUID(), {method:'PUT', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({goals: myGoals, custom_texts})});
  if(!r.ok){ toast((await r.json()).detail, true); return; }
  await loadGoals();
  toast(myGoals.length ? `✓ Journal updated — ${myGoals.length} tracking goal${myGoals.length>1?'s':''} (${myGoals.map(k => goalRegistry[k].label).join(', ')})` : '✓ Goals cleared — journal shows base fields only');
}

function goalFieldInput(f){
  if(f.type === 'rating'){
    return `<select class="inp gf" data-gkey="${esc(f.key)}" data-gtype="rating">
      <option value="">—</option>${[1,2,3,4,5].map(n => `<option value="${n}">${n}</option>`).join('')}
    </select>`;
  }
  if(f.type === 'number'){
    return `<input type="number" step="any" class="inp gf" data-gkey="${esc(f.key)}" data-gtype="number" placeholder="optional">`;
  }
  return `<input type="text" maxlength="200" class="inp gf" data-gkey="${esc(f.key)}" data-gtype="text" placeholder="optional">`;
}

/* ---------------- saved products ---------------- */
async function loadProducts(){
  savedProducts = (await jget('/api/products/' + currentUID())).products;
  renderProductChips();
  renderSettingsProducts();
}

function renderProductChips(){
  const box = document.getElementById('product-chips');
  box.innerHTML = savedProducts.length
    ? '<span class="text-xs text-slate-400 w-full">My products:</span>' +
      savedProducts.map(p => `<button type="button" class="chip" onclick="pickProduct(${p.id})"><span class="text-amber-400 inline-flex">${icon('star',13)}</span>${esc(p.name)}${p.default_unit ? ' · ' + esc(p.default_unit) : ''}</button>`).join('')
    : '';
}

function pickProduct(id){
  const p = savedProducts.find(x => x.id === id);
  if(!p) return;
  document.getElementById('u-name').value = p.name;
  document.getElementById('u-name').classList.remove('invalid');
  if(p.default_unit) document.getElementById('u-unit').value = p.default_unit;
  document.getElementById('u-save-product-row').classList.add('hidden');
}

function renderSettingsProducts(){
  const box = document.getElementById('settings-products');
  box.innerHTML = savedProducts.length ? savedProducts.map(p => `
    <div class="py-2.5 flex justify-between items-center gap-2">
      <div><span class="font-semibold">${esc(p.name)}</span>
        <span class="text-xs text-slate-400 block">${p.default_unit ? 'default unit: ' + esc(p.default_unit) : 'no default unit'}${esc(p.notes) ? ' • ' + esc(p.notes) : ''}</span></div>
      <button onclick="delProduct(${p.id})" class="text-rose-400 text-xs underline flex items-center gap-1">${icon('trash',13)}Delete</button>
    </div>`).join('')
    : '<p class="text-sm text-slate-500 italic py-2">No saved products yet — save one from the Log use sheet.</p>';
}

async function delProduct(id){
  await fetch(`/api/products/${currentUID()}/${id}`, {method:'DELETE'});
  await loadProducts();
  toast('Product removed from my list');
}

/* ---------------- sheets ---------------- */
let editingUsageId = null, editingObservationId = null;

function openFabChooser(){ document.getElementById('fab-chooser').classList.remove('hidden'); }
function closeFabChooser(){ document.getElementById('fab-chooser').classList.add('hidden'); }

// ISO timestamp -> local datetime-local input value (edit prefill)
function toLocalInput(iso){
  const d = new Date(iso);
  if(isNaN(d)) return '';
  const p = n => String(n).padStart(2,'0');
  return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+'T'+p(d.getHours())+':'+p(d.getMinutes());
}

function newIdemKey(){
  return (crypto && crypto.randomUUID) ? crypto.randomUUID()
    : 'k' + Date.now() + '-' + Math.random().toString(36).slice(2);
}

function openLogSheet(entryId){
  editingUsageId = entryId || null;
  const form = document.querySelector('#log-sheet form');
  form.dataset.idem = newIdemKey();  // one key per form session: a retry can never double-create
  delete form.dataset.override;
  document.getElementById('log-sheet').classList.remove('hidden');
  document.getElementById('log-sheet-title').innerText = editingUsageId ? 'Correct entry' : 'Log use';
  document.getElementById('u-submit-label').innerText = editingUsageId ? 'Save correction' : 'Save entry';
  const e = editingUsageId ? lastUsage.find(x => x.id === editingUsageId) : null;
  if(e){
    document.getElementById('u-name').value = e.peptide_name;
    document.getElementById('u-amount').value = e.amount;
    document.getElementById('u-unit').value = e.unit;
    document.getElementById('u-notes').value = e.notes || '';
    document.getElementById('u-when').value = toLocalInput(e.taken_at);
    document.getElementById('u-save-product-row').classList.add('hidden');
  } else {
    // New entries always open completely blank (A.1) — no leftover values.
    form.reset();
    document.getElementById('u-when').value = localDT();
    document.getElementById('u-save-product').checked = false;
    document.getElementById('u-save-product-row').classList.toggle('hidden',
      savedProducts.some(p => p.name.toLowerCase() === document.getElementById('u-name').value.trim().toLowerCase()));
  }
  clearErrors(form);
  setTimeout(() => document.getElementById('u-name').focus(), 60);
}
function closeLogSheet(){ editingUsageId = null; document.getElementById('log-sheet').classList.add('hidden'); }
function openObservationSheet(entryId){
  editingObservationId = entryId || null;
  document.querySelector('#observation-sheet form').dataset.idem = newIdemKey();
  document.getElementById('observation-sheet').classList.remove('hidden');
  document.getElementById('o-sheet-title').innerText = editingObservationId ? 'Correct observation' : 'Log an observation';
  document.getElementById('o-submit-label').innerText = editingObservationId ? 'Save correction' : 'Save observation';
  const box = document.getElementById('observation-fields');
  box.innerHTML = myGoals.length
    ? myGoals.flatMap(k => goalFieldsOf(k)).map(f => `<div><label class="block text-xs text-slate-400 mb-1">${esc(f.label)}</label>${goalFieldInput(f)}</div>`).join('')
    : '<p class="text-sm text-amber-300">No tracking goals selected yet — pick some in Settings → Tracking goals (e.g., Sleep, Height, Weight) to record observations.</p>';
  const e = editingObservationId ? lastObservations.find(x => x.id === editingObservationId) : null;
  if(e){
    document.getElementById('o-when').value = toLocalInput(e.taken_at);
    document.getElementById('o-notes').value = e.notes || '';
    box.querySelectorAll('.gf').forEach(el => {
      const v = e.goal_data && e.goal_data[el.dataset.gkey];
      if(v !== undefined) el.value = v;
    });
  } else {
    document.querySelector('#observation-sheet form').reset();  // A.1: new entries always open blank
    document.getElementById('o-when').value = localDT();
  }
  clearErrors(document.querySelector('#observation-sheet form'));
}
function closeObservationSheet(){ editingObservationId = null; document.getElementById('observation-sheet').classList.add('hidden'); }
async function logObservation(ev){
  ev.preventDefault();
  const form = ev.target, submit = document.getElementById('o-submit');
  clearErrors(form);
  const data = {};
  form.querySelectorAll('.gf').forEach(el => {
    if(el.value === '' || el.value === null) return;
    data[el.dataset.gkey] = el.dataset.gtype === 'rating' || el.dataset.gtype === 'number'
      ? Number(el.value) : el.value;
  });
  const when = document.getElementById('o-when').value;
  const body = {
    notes: document.getElementById('o-notes').value,
    taken_at: when ? new Date(when).toISOString() : null,
    goal_data: Object.keys(data).length ? data : null
  };
  if(!body.goal_data){
    formError('o-error', 'Enter at least one observation value (or use the symptom sheet for symptoms).');
    return;
  }
  if(!guardBusy(form, submit)) return;
  try{
    if(editingObservationId){
      // Correction: values, timestamp and notes are editable; the previous
      // measurement set is preserved server-side in the correction history.
      const r = await fetch(`/api/observations/${currentUID()}/${editingObservationId}`,
        {method:'PATCH', headers:{'Content-Type':'application/json'},
         body: JSON.stringify({taken_at: body.taken_at, notes: body.notes, goal_data: body.goal_data})});
      if(!r.ok){ const d = await r.json(); formError('o-error', d.detail || 'Correction failed.'); return; }
      const changed = (await r.json()).changed;
      closeObservationSheet();
      toast(changed ? '✓ Observation corrected — previous values kept in its correction history'
                    : 'Nothing changed — no correction recorded');
      await loadAll();
      return;
    }
    body.idempotency_key = form.dataset.idem || newIdemKey();
    const r = await fetch('/api/observations/' + currentUID(), {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    if(!r.ok){ const d = await r.json(); formError('o-error', d.detail || 'Save failed.'); return; }
    const saved = await r.json();
    form.reset();
    closeObservationSheet();
    const savedFor = body.taken_at
      ? new Date(body.taken_at).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})
      : 'now';
    toast('✓ Observation saved for ' + savedFor + ' — no dose attached'
      + (saved.replayed ? ' (already saved — retry confirmed, not duplicated)' : ''));
    await loadAll();
  } finally {
    releaseBusy(form, submit);
  }
}
function openSymptomSheet(){
  document.querySelector('#symptom-sheet form').reset();  // A.1: always blank
  document.getElementById('s-severity').value = '3';
  document.getElementById('symptom-sheet').classList.remove('hidden');
  clearErrors(document.querySelector('#symptom-sheet form'));
  setTimeout(() => document.getElementById('s-name').focus(), 60);
}
function closeSymptomSheet(){ document.getElementById('symptom-sheet').classList.add('hidden'); }

/* ---------------- profiles ---------------- */
function currentUID(){ return localStorage.getItem('pst_user'); }
function currentUser(){ return users.find(u => String(u.id) === String(currentUID())); }

async function refreshUsers(){
  users = (await jget('/api/users')).users;
  const me = currentUser();
  document.getElementById('profile-chip').innerText =
    me ? me.display_name + (me.is_demo ? ' (demo)' : '') : '—';
  document.getElementById('demo-banner').classList.toggle('hidden', !(me && me.is_demo));
  document.getElementById('dash-sub').innerText =
    me ? `Profile: ${me.display_name}${me.age ? ' • age ' + me.age : ''}${me.tracking_note ? ' • ' + me.tracking_note : ''}` : '';
  const list = document.getElementById('profiles-list');
  if(list) list.innerHTML = users.map(u => `
    <div class="py-2 flex justify-between items-center">
      <div><span class="font-semibold">${esc(u.display_name)}${u.is_demo ? ' (demo)' : ''}</span>
        <span class="text-xs text-slate-400 block">${u.age ? 'age ' + u.age + ' • ' : ''}${esc(u.tracking_note || '')}</span></div>
      ${String(u.id) === String(currentUID())
        ? '<span class="text-xs text-emerald-400 font-bold">Current</span>'
        : `<button onclick="switchProfile(${u.id})" class="text-xs text-sky-400 underline">Switch</button>`}
    </div>`).join('');
}

async function switchProfile(id){
  localStorage.setItem('pst_user', id);
  await refreshUsers();
  await loadAll();
  switchTab('today');
}

function saveProfile(){
  const age = document.getElementById('set-age').value;
  const note = document.getElementById('set-note').value;
  fetch('/api/users/' + currentUID(), {method:'PATCH', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({age: age || null, tracking_note: note})})
    .then(r => { if(!r.ok) throw new Error(); return r.json(); })
    .then(() => { refreshUsers(); })
    .catch(e => alert('Save failed'));
}

async function resetDemo(){
  await fetch('/api/demo/reset', {method:'POST'});
  await refreshUsers();
  await loadAll();
}

/* ---------------- loading ---------------- */
async function loadAll(){
  if(!currentUID()) return;
  const uid = currentUID();
  const [usage, symptoms, reminders, observations] = await Promise.all([
    jget('/api/usage/' + uid).then(d => d.usage),
    jget('/api/symptoms/' + uid).then(d => d.symptoms),
    jget('/api/reminders/' + uid).then(d => d.reminders),
    jget('/api/observations/' + uid).then(d => d.observations)
  ]);
  lastUsage = usage; lastSymptoms = symptoms; lastReminders = reminders; lastObservations = observations;
  document.getElementById('today-date').innerText = new Date().toLocaleDateString(undefined,{weekday:'long',month:'long',day:'numeric'});
  document.getElementById('stat-usage').innerText = usage.length;
  document.getElementById('stat-symptoms').innerText = symptoms.length;
  document.getElementById('stat-reminders').innerText = reminders.filter(r => r.enabled).length;
  renderDueToday(reminders);
  renderLoggedToday(usage);
  renderHistory();
  renderReminders(reminders);
  renderCatalog();
  loadBrands();
  await loadProducts();
  await loadGoals();
  const me = currentUser();
  if(me){ document.getElementById('set-age').value = me.age ?? ''; document.getElementById('set-note').value = me.tracking_note ?? ''; }
}

function renderDueToday(reminders){
  const dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const today = dayNames[new Date().getDay()];
  const due = reminders.filter(r => r.enabled &&
    (r.days.toLowerCase().includes('daily') ||
     r.days.split(',').map(d => d.trim().toLowerCase()).includes(today.toLowerCase())));
  document.getElementById('due-today').innerHTML = due.length ? due.map(e => `
    <div class="py-2.5 flex justify-between items-center gap-2">
      <div><span class="font-semibold">${esc(e.peptide_name)}</span>
        <span class="font-mono text-sky-400">${e.time_of_day}</span>
        <span class="text-xs text-slate-400 block">${esc(e.days)}</span></div>
      <button onclick="toggleReminder(${e.id}, 0)" class="text-xs text-slate-400 underline">Pause</button>
    </div>`).join('')
    : '<p class="text-sm text-slate-500 italic py-2">Nothing scheduled for today.</p>';
}

function renderLoggedToday(usage){
  const today = new Date().toISOString().slice(0,10);
  const todays = usage.filter(e => (e.taken_at || '').slice(0,10) === today);
  document.getElementById('logged-today').innerHTML = todays.length ? todays.map(e => `
    <div class="py-2.5 flex justify-between items-center">
      <div><span class="font-semibold">${esc(e.peptide_name)}</span>
        <span class="font-mono text-emerald-400">${e.amount} ${e.unit}</span></div>
      <span class="text-xs text-slate-400">${fmtDate(e.taken_at)}</span>
    </div>`).join('')
    : '<p class="text-sm text-slate-500 italic py-2">Nothing logged today yet.</p>';
}

/* ---------------- history filters + corrections ---------------- */
let histFilter = {product:'', from:'', to:'', type:'all'};

function histFiltersActive(){
  return !!(histFilter.product || histFilter.from || histFilter.to || histFilter.type !== 'all');
}

function readHistFilters(){
  histFilter = {
    product: (document.getElementById('f-product').value || '').trim().toLowerCase(),
    from: document.getElementById('f-from').value || '',
    to: document.getElementById('f-to').value || '',
    type: document.getElementById('f-type').value || 'all'
  };
}

function clearHistFilters(){
  document.getElementById('f-product').value = '';
  document.getElementById('f-from').value = '';
  document.getElementById('f-to').value = '';
  document.getElementById('f-type').value = 'all';
  renderHistory();
}

function inDateRange(iso){
  if(!histFilter.from && !histFilter.to) return true;
  const d = new Date(iso);
  if(isNaN(d)) return true;  // unparseable timestamps are never hidden
  const p = n => String(n).padStart(2,'0');
  const day = d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate());
  if(histFilter.from && day < histFilter.from) return false;
  if(histFilter.to && day > histFilter.to) return false;
  return true;
}

function productMatch(name){
  return !histFilter.product || String(name || '').toLowerCase().includes(histFilter.product);
}

function emptyHistMessage(allCount){
  return allCount && histFiltersActive()
    ? '<p class="text-sm text-slate-500 italic py-2">No entries match the current filters — adjust or clear them above.</p>'
    : null;
}

// Correction history display (spec: corrections visible in History with
// timestamps; original values preserved).
const CORR_LABELS = {peptide_name:'product', amount:'amount', unit:'unit',
                     route:'route', taken_at:'when', notes:'notes',
                     goal_data:'measurements'};
function corrValue(k, v){
  if(k === 'taken_at') return fmtDate(v);
  if(k === 'goal_data') return Object.entries(v || {}).map(([f, x]) => fieldLabel(f) + ' ' + x).join(', ');
  return String(v);
}
function correctionsHtml(corrs){
  if(!corrs || !corrs.length) return '';
  const lines = corrs.map(c => '<div>• Edited ' + fmtDate(c.edited_at) + ' — before: '
    + Object.entries(c.previous || {}).map(([k, v]) =>
        esc(CORR_LABELS[k] || k) + ': ' + esc(corrValue(k, v))).join(', ')
    + '</div>').join('');
  return '<div class="text-amber-300">✎ Edited — every change kept with its time<div class="space-y-0.5 text-xs text-slate-400">' + lines + '</div></div>';
}

function renderHistory(){
  readHistFilters();
  const show = t => histFilter.type === 'all' || histFilter.type === t;
  document.getElementById('usage-history-card').classList.toggle('hidden', !show('usage'));
  document.getElementById('symptom-history-card').classList.toggle('hidden', !show('symptom'));
  document.getElementById('observation-history-card').classList.toggle('hidden', !show('observation'));
  renderUsage(lastUsage);
  renderSymptoms(lastSymptoms);
  renderObservations(lastObservations);
  const n = (histFilter.type === 'all' || histFilter.type === 'usage' ? lastUsage.filter(e => inDateRange(e.taken_at) && productMatch(e.peptide_name)).length : 0)
    + (histFilter.type === 'all' || histFilter.type === 'observation' ? lastObservations.filter(e => inDateRange(e.taken_at)).length : 0)
    + (histFilter.type === 'all' || histFilter.type === 'symptom' ? lastSymptoms.filter(e => inDateRange(e.logged_at) && productMatch(e.peptide_name)).length : 0);
  document.getElementById('f-status').innerText = histFiltersActive()
    ? n + ' matching ' + (n === 1 ? 'event' : 'events') + ' shown'
    : '';
}

function renderUsage(usage){
  const rows = usage.filter(e => inDateRange(e.taken_at) && productMatch(e.peptide_name));
  const noneMsg = emptyHistMessage(usage.length) || '<p class="text-sm text-slate-500 italic py-2">No usage logged yet.</p>';
  document.getElementById('usage-list').innerHTML = rows.length ? rows.map(e => `
    <details class="py-2.5">
      <summary class="flex justify-between items-center gap-2">
        <div><span class="font-semibold">${esc(e.peptide_name)}</span>
          <span class="font-mono text-emerald-400">${e.amount} ${e.unit}</span>
          ${e.corrections && e.corrections.length ? '<span class="text-amber-300 text-xs ml-1">✎ edited</span>' : ''}</div>
        <span class="text-xs text-slate-400">${fmtDate(e.taken_at)}</span>
      </summary>
      <div class="text-xs text-slate-400 mt-1.5 space-y-1">
        <div>Full timestamp: ${esc(e.taken_at)}</div>
        ${e.brand_name ? '<div>Brand (unrated): ' + esc(e.brand_name) + '</div>' : ''}
        ${e.notes ? '<div>Notes: ' + esc(e.notes) + '</div>' : ''}
        ${e.goal_data ? '<div>' + Object.entries(e.goal_data).map(([k, v]) => {
            return esc(fieldLabel(k)) + ': ' + esc(String(v));
          }).join(' • ') + '</div>' : ''}
        ${correctionsHtml(e.corrections)}
        <div class="flex gap-3 pt-1">
          <button onclick="openLogSheet(${e.id})" class="text-sky-400 underline">Edit / correct</button>
          <button onclick="delUsage(${e.id})" class="text-rose-400 underline">Delete entry</button>
        </div>
      </div>
    </details>`).join('') : noneMsg;
}

function renderSymptoms(symptoms){
  const rows = symptoms.filter(e => inDateRange(e.logged_at) && productMatch(e.peptide_name));
  const noneMsg = emptyHistMessage(symptoms.length) || '<p class="text-sm text-slate-500 italic py-2">No symptoms logged.</p>';
  document.getElementById('symptom-list').innerHTML = rows.length ? rows.map(e => `
    <details class="py-2.5">
      <summary class="flex justify-between items-center gap-2">
        <div><span class="font-semibold">${esc(e.peptide_name)}</span>
          <span class="text-amber-400 font-mono text-sm">sev ${e.severity}/5</span></div>
        <span class="text-xs text-slate-400">${fmtDate(e.logged_at)}</span>
      </summary>
      <div class="text-xs text-slate-400 mt-1.5 space-y-1">
        <div class="text-sm text-slate-300">${esc(e.description)}</div>
        <div>Full timestamp: ${esc(e.logged_at)}</div>
        <button onclick="delSymptom(${e.id})" class="text-rose-400 underline">Delete entry</button>
      </div>
    </details>`).join('') : noneMsg;
}

function obsRowHtml(e, allowEdit){
  return `
    <details class="py-2.5">
      <summary class="flex justify-between items-center gap-2">
        <div><span class="font-semibold text-sky-300">Observation</span>
          <span class="text-xs text-slate-400">${Object.keys(e.goal_data || {}).map(k => esc(fieldLabel(k))).join(', ')}</span>
          ${e.corrections && e.corrections.length ? '<span class="text-amber-300 text-xs ml-1">✎ edited</span>' : ''}</div>
        <span class="text-xs text-slate-400">${fmtDate(e.taken_at)}</span>
      </summary>
      <div class="text-xs text-slate-400 mt-1.5 space-y-1">
        <div>Full timestamp: ${esc(e.taken_at)}</div>
        ${e.goal_data ? '<div class="text-sm text-slate-300">' + Object.entries(e.goal_data).map(([k, v]) =>
            esc(fieldLabel(k)) + ': ' + esc(String(v))).join(' • ') + '</div>' : ''}
        ${e.notes ? '<div>Notes: ' + esc(e.notes) + '</div>' : ''}
        ${correctionsHtml(e.corrections)}
        <div class="flex gap-3 pt-1">
          ${allowEdit ? '<button onclick="openObservationSheet(' + e.id + ')" class="text-sky-400 underline">Edit / correct</button>' : ''}
          <button onclick="delObservation(${e.id})" class="text-rose-400 underline">Delete entry</button>
        </div>
      </div>
    </details>`;
}

function renderObservations(observations){
  // Today card: always unfiltered. History card: date filter applies
  // (observations carry no product, so the product filter never hides them).
  document.getElementById('observation-list').innerHTML = observations.length
    ? observations.map(e => obsRowHtml(e, false)).join('')
    : '<p class="text-sm text-slate-500 italic py-2">No observations yet — sleep, height, weight, etc. can be recorded without any dose.</p>';
  const hist = document.getElementById('observation-history');
  if(hist){
    const rows = observations.filter(e => inDateRange(e.taken_at));
    const noneMsg = emptyHistMessage(observations.length)
      || '<p class="text-sm text-slate-500 italic py-2">No observations in this period.</p>';
    hist.innerHTML = rows.length ? rows.map(e => obsRowHtml(e, true)).join('') : noneMsg;
  }
}

/* ---------------- printable visit summary ---------------- */
// Readable, printable summary for a selected date range. Separates actual
// administrations, observations, and planned reminders; includes units and
// timestamps; carries a user-entered-data disclaimer and makes NO claims
// about cause, effect, or treatment effectiveness.
function openVisitSummary(){
  readHistFilters();
  // default range: the last 30 days
  if(!histFilter.from || !histFilter.to){
    const p = n => String(n).padStart(2,'0');
    const now = new Date();
    const from = new Date(now); from.setDate(from.getDate() - 30);
    document.getElementById('f-from').value = from.getFullYear()+'-'+p(from.getMonth()+1)+'-'+p(from.getDate());
    document.getElementById('f-to').value = now.getFullYear()+'-'+p(now.getMonth()+1)+'-'+p(now.getDate());
    readHistFilters();
  }
  const me = currentUser();
  const profile = me ? esc(me.display_name) : '(unknown profile)';
  const admin = lastUsage.filter(e => inDateRange(e.taken_at) && productMatch(e.peptide_name));
  const obs = lastObservations.filter(e => inDateRange(e.taken_at));
  const symp = lastSymptoms.filter(e => inDateRange(e.logged_at) && productMatch(e.peptide_name));
  if(!admin.length && !obs.length && !symp.length){
    toast('No records in that date range — nothing to summarize.', true);
    return;
  }
  const range = histFilter.from + ' to ' + histFilter.to;
  const sec = (title, body) => body ? `<h2 style="font-size:15px;margin:18px 0 6px;border-bottom:2px solid #333;padding-bottom:3px;">${title}</h2>${body}` : '';
  const adminRows = admin.map(e => {
    const edited = e.corrections && e.corrections.length
      ? ' <em>[edited ' + e.corrections.length + '× — previous: ' + esc(e.corrections.map(c =>
          Object.entries(c.previous || {}).map(([k, v]) => (CORR_LABELS[k] || k) + ' ' + corrValue(k, v)).join(', ')).join('; ')) + ']</em>'
      : '';
    return '<li style="margin:4px 0;">' + esc(fmtDate(e.taken_at)) + ' — <strong>' + esc(e.peptide_name) + '</strong>, '
      + esc(String(e.amount)) + ' ' + esc(e.unit)
      + (e.notes ? ' — notes: ' + esc(e.notes) : '') + edited + '</li>';
  }).join('');
  const obsRows = obs.map(e => {
    const edited = e.corrections && e.corrections.length ? ' <em>[edited]</em>' : '';
    return '<li style="margin:4px 0;">' + esc(fmtDate(e.taken_at)) + ' — '
      + esc(Object.entries(e.goal_data || {}).map(([k, v]) => fieldLabel(k) + ': ' + v).join('; '))
      + (e.notes ? ' — notes: ' + esc(e.notes) : '') + edited + '</li>';
  }).join('');
  const sympRows = symp.map(e =>
    '<li style="margin:4px 0;">' + esc(fmtDate(e.logged_at)) + ' — <strong>' + esc(e.peptide_name)
    + '</strong>, severity ' + esc(String(e.severity)) + '/5 (self-rated) — ' + esc(e.description) + '</li>').join('');
  const remRows = lastReminders.map(e =>
    '<li style="margin:4px 0;">' + esc(e.peptide_name) + ' at ' + esc(e.time_of_day)
    + ' (' + esc(e.days) + (e.enabled ? ', active' : ', paused') + ')</li>').join('');
  const generated = new Date().toLocaleString();
  const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Visit summary — ${profile} — ${range}</title>
<style>
  body{font-family:Georgia,serif;max-width:720px;margin:24px auto;color:#111;line-height:1.45;padding:0 16px;}
  h1{font-size:20px;margin:0 0 2px;} .sub{color:#555;font-size:12px;margin-bottom:4px;}
  table{border-collapse:collapse;width:100%;font-size:13px;} th,td{border:1px solid #999;padding:4px 8px;text-align:left;vertical-align:top;}
  .disclaimer{background:#fdf3d8;border:1px solid #d9c26a;padding:10px 12px;font-size:12px;margin-top:22px;border-radius:4px;}
  @media print{.noprint{display:none}}
</style></head><body>
<button class="noprint" onclick="window.print()" style="float:right;padding:6px 14px;cursor:pointer;">Print</button>
<h1>Personal record summary</h1>
<div class="sub">Profile: ${profile} · Date range: ${esc(range)} · Generated ${esc(generated)} · Peptide Safety Tracker (local app)</div>
${sec('Actual administrations (as entered by you)', admin.length ? '<ul style="padding-left:18px;font-size:13px;">' + adminRows + '</ul>' : '')}
${sec('Observations (recorded on their own — no dose attached)', obs.length ? '<ul style="padding-left:18px;font-size:13px;">' + obsRows + '</ul>' : '')}
${sec('Symptoms (self-rated severity)', symp.length ? '<ul style="padding-left:18px;font-size:13px;">' + sympRows + '</ul>' : '')}
${sec('Planned reminders (schedule only — not a record of anything taken)', remRows ? '<ul style="padding-left:18px;font-size:13px;">' + remRows + '</ul>' : '')}
<div class="disclaimer"><strong>Disclaimer — user-entered data.</strong> Everything above is what was typed into this app for this profile; the app does not verify it. This summary is <strong>not medical advice</strong>, is not a clinical document, and implies <strong>nothing about cause, effect, or treatment effectiveness</strong>. Gaps mean nothing was recorded — not that nothing happened. Entries marked [edited] were corrected later; the app keeps the original values. Share this with a licensed clinician, not with anyone else.</div>
</body></html>`;
  const w = window.open('', '_blank');
  if(!w){ toast('Popup blocked — allow popups for this page to print the summary.', true); return; }
  w.document.write(html);
  w.document.close();
}

async function delObservation(id){
  await fetch(`/api/observations/${currentUID()}/${id}`, {method:'DELETE'});
  loadAll();
}

function renderReminders(reminders){
  document.getElementById('reminder-list').innerHTML = reminders.length ? reminders.map(e => `
    <div class="py-2.5 flex justify-between gap-2 items-center">
      <div><span class="font-semibold">${esc(e.peptide_name)}</span>
        <span class="font-mono text-sky-400">${e.time_of_day}</span>
        <span class="text-xs text-slate-400 block">${esc(e.days)} ${e.enabled ? '' : '• disabled'}</span></div>
      <div class="flex gap-3">
        <button onclick="toggleReminder(${e.id}, ${e.enabled ? 0 : 1})" class="text-sky-400 text-xs underline">${e.enabled ? 'Pause' : 'Resume'}</button>
        <button onclick="delReminder(${e.id})" class="text-rose-400 text-xs underline">Delete</button>
      </div>
    </div>`).join('') : '<p class="text-sm text-slate-500 italic py-2">No reminders configured.</p>';
}

const STATUS = {
  'fda-approved': {label: 'Approved products exist (ingredient-level)',
                   cls: 'bg-sky-950 text-sky-300 border-sky-800',
                   note: 'Approval applies to specific products only — verify the exact product.'},
  'not-fda-approved': {label: 'No FDA-approved product',
                       cls: 'bg-rose-950 text-rose-300 border-rose-800',
                       note: 'No FDA-approved human use for this ingredient.'},
  'compounding-flagged': {label: 'FDA compounding context',
                          cls: 'bg-amber-950 text-amber-300 border-amber-800',
                          note: 'FDA has published risk discussion — read it directly.'},
  'unknown': {label: 'Status unknown — verify manually',
              cls: 'bg-slate-800 text-slate-300 border-slate-700',
              note: ''}
};

const REVIEW_STATUS = {
  'verified': {label: 'Source checked', cls: 'text-emerald-400', icon: 'check'},
  'awaiting-verification': {label: 'Awaiting verification', cls: 'text-amber-400', icon: 'warn'}
};

async function loadCatalog(){ catalog = (await jget('/api/catalog')).catalog; renderCatalog(); }

function renderCatalog(){
  const raw = (document.getElementById('cat-search').value || '').trim();
  const q = raw.toLowerCase();
  const list = catalog.filter(c =>
    (c.name + ' ' + c.category + ' ' + (c.aliases || []).join(' ')).toLowerCase().includes(q));
  // HGH searches get the required sourced educational note, and the
  // relationship is explained rather than silently substituted.
  const hghNote = document.getElementById('hgh-search-note');
  const hghHit = q && (q === 'hgh' || q.includes('hgh') || q.includes('growth hormone'));
  hghNote.classList.toggle('hidden', !hghHit);
  if(hghHit){
    hghNote.innerHTML = '"HGH" is another name for <strong>somatropin</strong> (human growth hormone) — searching your own wording, not a product. <strong>Growth hormone is not a general height enhancer: once growth plates have fused, HGH does not increase height.</strong> This app cannot assess growth potential or recommend hormone treatment; discuss growth concerns with a qualified clinician. (<a class="text-amber-100 underline" href="https://my.clevelandclinic.org/health/articles/23309-human-growth-hormone-hgh" target="_blank" rel="noopener">Cleveland Clinic</a> · <a class="text-amber-100 underline" href="https://medlineplus.gov/druginfo/meds/a622022.html" target="_blank" rel="noopener">MedlinePlus</a>)';
  }
  document.getElementById('catalog-list').innerHTML = list.map(c => {
    const st = STATUS[c.regulatory_status] || STATUS['unknown'];
    const rv = REVIEW_STATUS[c.review_status] || REVIEW_STATUS['verified'];
    const aliasLine = (c.aliases || []).length
      ? `<p class="text-xs text-slate-500">Also listed as: ${c.aliases.map(a => esc(a)).join(', ')}${/hgh/i.test((c.aliases||[]).join(' ')) ? ' — “HGH” refers to this ingredient (see the note above), not a separate product' : ''}</p>`
      : '';
    return `<details class="bg-slate-900 border border-slate-800 rounded-xl">
      <summary class="p-4 flex justify-between items-start gap-2">
        <div><span class="font-semibold">${esc(c.name)}</span>
          <span class="text-xs text-slate-400 block">${esc(c.category)}</span></div>
        <span class="text-xs font-mono px-2.5 py-1 rounded-full border text-center ${st.cls}">${st.label}</span>
      </summary>
      <div class="px-4 pb-4 space-y-2 text-sm">
        ${aliasLine}
        <p class="text-slate-300 leading-relaxed">${esc(c.evidence_note)}</p>
        ${st.note ? `<p class="text-xs text-slate-400">${st.note}</p>` : ''}
        <p class="text-xs ${rv.cls} flex items-center gap-1.5">${icon(rv.icon, 13)} ${rv.label} · source: ${esc(c.source_type)}${c.last_reviewed ? ' · source-checked ' + esc(c.last_reviewed) : ''}</p>
        <a class="text-sm text-emerald-400 underline" href="${esc(c.source_url)}" target="_blank" rel="noopener">Open official source</a>
      </div>
    </details>`;
  }).join('') || '<p class="text-sm text-slate-500 italic py-2">No matches.</p>';
}

async function loadBrands(){
  const {brands} = await jget('/api/brands');
  document.getElementById('brand-list').innerHTML = brands.map(b => `
    <div class="py-2.5 flex justify-between items-center gap-2">
      <div><span class="font-semibold">${esc(b.name)}</span>
        <span class="text-xs text-slate-400 block">${esc(b.supplier_type)} • ${esc(b.region)} ${b.is_demo ? '• demo entry' : ''}</span></div>
      <span class="text-xs text-slate-400 whitespace-nowrap">No rating — use checklist</span>
    </div>`).join('');
}

/* ---------------- verification checklist ---------------- */
const CHECK_ITEMS = [
  {key: 'label', text: 'Exact product label exists on DailyMed',
   urlKey: 'dailymed_label_search'},
  {key: 'fda_records', text: 'FDA drug approval records reviewed (openFDA)',
   urlKey: 'openfda_drug_records'},
  {key: 'compounding', text: 'FDA compounding risk context read',
   urlKey: 'fda_compounding_page'},
  {key: 'seller', text: 'Seller licensure & prescription requirements checked',
   urlKey: 'fda_buying_medicine_online'}
];
function checkKey(product, key){ return 'pst_check_' + product.toLowerCase() + '_' + key; }

async function verify(){
  const name = document.getElementById('v-name').value.trim();
  if(!name) return;
  const {links} = await jget('/api/verify?name=' + encodeURIComponent(name));
  document.getElementById('verify-result').innerHTML = `
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-2">
      <p class="text-sm font-semibold">Checklist for "${esc(name)}"</p>
      <p class="text-xs text-slate-400">The app does not check anything for you and never scores a product. You mark each item when <em>you</em> have checked it; your marks (with dates) stay on this device.</p>
      ${CHECK_ITEMS.map(item => {
        const saved = localStorage.getItem(checkKey(name, item.key));
        return `<div class="flex items-start gap-3 bg-slate-950 border border-slate-800 rounded-lg p-3">
          <input type="checkbox" class="mt-1 w-4 h-4 accent-emerald-500" ${saved ? 'checked' : ''}
            onchange="markChecked('${esc(name).replace(/'/g, "\\'")}','${item.key}',this.checked)">
          <div class="flex-1">
            <span class="text-sm">${esc(item.text)}</span>
            <span class="text-xs block ${saved ? 'text-emerald-400' : 'text-slate-500'}">${saved ? 'Checked by you: ' + esc(saved) : 'Status: unknown — not checked yet'}</span>
          </div>
          <a class="text-xs text-emerald-400 underline whitespace-nowrap self-center" href="${esc(links[item.urlKey])}" target="_blank" rel="noopener">Open →</a>
        </div>`;
      }).join('')}
      <button onclick="clearChecks('${esc(name).replace(/'/g, "\\'")}')" class="text-xs text-slate-400 underline">Clear my marks</button>
      <p class="text-xs text-slate-500">${esc(links.disclaimer)}</p>
    </div>`;
}

function markChecked(product, key, checked){
  if(checked){
    localStorage.setItem(checkKey(product, key),
      new Date().toLocaleDateString(undefined,{year:'numeric',month:'short',day:'numeric'}));
  } else {
    localStorage.removeItem(checkKey(product, key));
  }
  verify();
}
function clearChecks(product){
  CHECK_ITEMS.forEach(i => localStorage.removeItem(checkKey(product, i.key)));
  verify();
}

/* ---------------- actions ---------------- */
function guardBusy(form, btn){
  if(form.dataset.busy) return false;
  form.dataset.busy = '1';
  if(btn){ btn.disabled = true; btn.classList.add('opacity-50','cursor-wait'); }
  return true;
}
function releaseBusy(form, btn){
  delete form.dataset.busy;
  if(btn){ btn.disabled = false; btn.classList.remove('opacity-50','cursor-wait'); }
}

async function logUsage(ev){
  ev.preventDefault();
  const form = ev.target, submit = document.getElementById('u-submit');
  const name = document.getElementById('u-name'), amount = document.getElementById('u-amount');
  clearErrors(form);
  const nameVal = name.value.trim();
  const amountVal = parseFloat(amount.value);
  if(!nameVal){ formError('u-error', 'Enter a product or peptide name.', name); name.focus(); return; }
  if(!(amountVal > 0)){ formError('u-error', 'Amount must be a number greater than 0.', amount); amount.focus(); return; }
  if(!guardBusy(form, submit)) return;
  try{
    const when = document.getElementById('u-when').value;
    const body = {
      peptide_name: nameVal,
      amount: amountVal,
      unit: document.getElementById('u-unit').value,
      notes: document.getElementById('u-notes').value,
      taken_at: when ? new Date(when).toISOString() : null,
      override_duplicate: form.dataset.override === '1'
    };
    if(editingUsageId){
      // Correction: PATCH with the editable fields; the server preserves the
      // previous values and records the correction timestamp.
      const r = await fetch(`/api/usage/${currentUID()}/${editingUsageId}`,
        {method:'PATCH', headers:{'Content-Type':'application/json'},
         body: JSON.stringify({peptide_name: body.peptide_name, amount: body.amount,
           unit: body.unit, taken_at: body.taken_at, notes: body.notes})});
      if(!r.ok){ const d = await r.json(); formError('u-error', d.detail || 'Correction failed.'); return; }
      const changed = (await r.json()).changed;
      closeLogSheet();
      toast(changed ? '✓ Entry corrected — the previous values and time are kept in its correction history'
                    : 'Nothing changed — no correction recorded');
      await loadAll();
      return;
    }
    // Idempotency: a retried submission with the same key replays the first
    // response instead of creating a second event (separate from the
    // duplicate guard below).
    body.idempotency_key = form.dataset.idem || newIdemKey();
    const r = await fetch('/api/usage/' + currentUID(), {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    if(r.status === 409){
      // Server-side duplicate guard: prompt without blocking an override.
      const d = await r.json();
      formError('u-error', (d.detail || 'Possible duplicate.') + ' Choose Save entry again to keep both.');
      form.dataset.override = '1';
      return;
    }
    if(!r.ok){ const d = await r.json(); formError('u-error', d.detail || 'Save failed.'); return; }
    const saved = await r.json();
    const savedId = saved.entry_id;
    delete form.dataset.override;
    if(document.getElementById('u-save-product').checked &&
       !savedProducts.some(p => p.name.toLowerCase() === nameVal.toLowerCase())){
      const pr = await fetch('/api/products/' + currentUID(), {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({name: nameVal, default_unit: body.unit})});
      if(pr.ok) await loadProducts();
    }
    form.reset();
    document.getElementById('u-save-product-row').classList.add('hidden');
    closeLogSheet();
    const savedFor = body.taken_at
      ? new Date(body.taken_at).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})
      : 'now';
    toast('✓ Saved ' + nameVal + ' (' + body.amount + ' ' + body.unit + ') for ' + savedFor
      + (saved.replayed ? ' (already saved — retry confirmed, not duplicated)' : ''),
      false,
      {label: 'Undo', run: async () => {
        await fetch(`/api/usage/${currentUID()}/${savedId}`, {method:'DELETE'});
        toast('Entry deleted');
        loadAll();
      }});
    await loadAll();
  } finally {
    releaseBusy(form, submit);
  }
}

async function logSymptom(ev){
  ev.preventDefault();
  const form = ev.target, submit = document.getElementById('s-submit');
  const name = document.getElementById('s-name'), desc = document.getElementById('s-desc');
  clearErrors(form);
  if(!name.value.trim()){ formError('s-error', 'Enter which product this relates to.', name); name.focus(); return; }
  if(!desc.value.trim()){ formError('s-error', 'Describe what you felt.', desc); desc.focus(); return; }
  if(!guardBusy(form, submit)) return;
  try{
    const body = {
      peptide_name: name.value.trim(),
      severity: parseInt(document.getElementById('s-severity').value),
      description: desc.value.trim()
    };
    const r = await fetch('/api/symptoms/' + currentUID(), {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    if(!r.ok){ const d = await r.json(); formError('s-error', d.detail || 'Save failed.'); return; }
    form.reset();
    document.getElementById('s-severity').value = '3';
    closeSymptomSheet();
    toast('✓ Symptom saved (severity ' + body.severity + '/5)');
    await loadAll();
  } finally {
    releaseBusy(form, submit);
  }
}

/* ---------------- reminders ---------------- */
const REMINDER_DAYS = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
let reminderDays = [];
function renderReminderChips(){
  const box = document.getElementById('r-days-chips');
  box.innerHTML = REMINDER_DAYS.map(d => `
    <button type="button" class="chip ${reminderDays.includes(d) ? '!border-sky-500 !bg-sky-950' : ''}"
      onclick="toggleReminderDay('${d}')">${d}</button>`).join('')
    + `<button type="button" class="chip ${reminderDays.length === 7 ? '!border-sky-500 !bg-sky-950' : ''}"
      onclick="setAllReminderDays()">Every day</button>`;
}
function toggleReminderDay(d){
  reminderDays = reminderDays.includes(d) ? reminderDays.filter(x => x !== d) : [...reminderDays, d];
  renderReminderChips();
}
function setAllReminderDays(){
  reminderDays = reminderDays.length === 7 ? [] : [...REMINDER_DAYS];
  renderReminderChips();
}

// Honest notification status (usability spec: show permission + delivery
// status, offer a test notification, label in-app-only limits).
function refreshNotifStatus(){
  const el = document.getElementById('notif-status');
  if(!el) return;
  if(!('Notification' in window)){
    el.textContent = 'Browser notifications: not supported here — reminders stay in-app (this page).';
  } else if(Notification.permission === 'granted'){
    el.textContent = 'Browser permission: granted — test notifications can fire while this tab is open. Reminders still do not deliver when the app is closed.';
  } else if(Notification.permission === 'denied'){
    el.textContent = 'Browser permission: denied by you — reminders stay in-app only. Reset it in your browser site settings if you change your mind.';
  } else {
    el.textContent = 'Browser permission: not asked yet — reminders already work in-app without it.';
  }
}
async function testNotification(){
  if(!('Notification' in window)){
    toast('This browser does not support notifications — reminders remain in-app only.', true);
    return;
  }
  let perm = Notification.permission;
  if(perm === 'default'){
    perm = await Notification.requestPermission();
  }
  refreshNotifStatus();
  if(perm === 'granted'){
    new Notification('Peptide Safety Tracker', {body: 'Test reminder — shown only while this app is open.'});
    toast('✓ Test notification sent (in-app / open tab only)');
  } else {
    toast('Permission denied — reminders stay in-app only (this page).', true);
  }
}

async function addReminder(ev){
  ev.preventDefault();
  const form = ev.target, submit = document.getElementById('r-submit');
  const name = document.getElementById('r-name'), time = document.getElementById('r-time'), days = document.getElementById('r-days');
  clearErrors(form);
  if(!name.value.trim()){ formError('r-error', 'Enter a product name.', name); name.focus(); return; }
  if(!time.value){ formError('r-error', 'Pick a time of day.', time); time.focus(); return; }
  const daysVal = reminderDays.length === 7 ? 'Daily' : reminderDays.join(',');
  if(!daysVal){ formError('r-error', 'Pick at least one day (or “Every day”).'); return; }
  days.value = daysVal;
  if(!guardBusy(form, submit)) return;
  try{
    const body = {peptide_name: name.value.trim(), time_of_day: time.value, days: daysVal};
    const r = await fetch('/api/reminders/' + currentUID(), {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    if(!r.ok){ const d = await r.json(); formError('r-error', d.detail || 'Save failed.'); return; }
    form.reset();
    reminderDays = [];
    renderReminderChips();
    toast('✓ Reminder set — ' + body.peptide_name + ' at ' + body.time_of_day + ' (in-app only)');
    await loadAll();
  } finally {
    releaseBusy(form, submit);
  }
}

async function toggleReminder(id, enabled){
  await fetch(`/api/reminders/${currentUID()}/${id}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({enabled})});
  loadAll();
}
async function delReminder(id){ await fetch(`/api/reminders/${currentUID()}/${id}`, {method:'DELETE'}); loadAll(); }
async function delUsage(id){ await fetch(`/api/usage/${currentUID()}/${id}`, {method:'DELETE'}); loadAll(); }
async function delSymptom(id){ await fetch(`/api/symptoms/${currentUID()}/${id}`, {method:'DELETE'}); loadAll(); }

function exportData(fmt){ window.location.href = `/api/export/${currentUID()}?fmt=${fmt}`; }

/* ---------------- boot ---------------- */
(async function(){
  users = (await jget('/api/users')).users;
  await loadCatalog();
  renderIcons();
  attachPicker('u-name', 'u-name-dd', it => {
    document.getElementById('u-save-product-row').classList.toggle('hidden',
      it.src === 'saved' || savedProducts.some(p => p.name.toLowerCase() === it.name.toLowerCase()));
  });
  attachPicker('s-name', 's-name-dd');
  attachPicker('r-name', 'r-name-dd');
  renderReminderChips();
  refreshNotifStatus();
  const saved = localStorage.getItem('pst_user');
  if(saved && users.find(u => String(u.id) === String(saved))){
    await enterApp();
  } else {
    await showStart();
  }
})();
</script>
</body>
</html>
"""


def _build_html():
    return HTML_CONTENT.replace("__DISCLAIMER__", DISCLAIMER)


HTML_CONTENT = _build_html()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("peptide_safety.server:app", host="127.0.0.1", port=8001)
