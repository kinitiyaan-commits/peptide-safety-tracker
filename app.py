import sqlite3
from fastapi import FastAPI, Query, Body
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="Apex Fitness Unified Engine")
DB_PATH = "fitness_tracker.db"

def init_user_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profile (
            id INTEGER PRIMARY KEY DEFAULT 1,
            age INTEGER, gender TEXT, height_in REAL, weight_lbs REAL,
            activity TEXT, goal TEXT, diet_preference TEXT,
            plan_mode TEXT DEFAULT 'auto',
            target_calories REAL, target_protein REAL, target_carbs REAL, target_fat REAL,
            target_sugar REAL, target_fiber REAL
        )
    """)
    
    # Wger / Hevy-style Exercise & Machine Database
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, category TEXT, equipment TEXT, description TEXT
        )
    """)
    
    # Peptides Database Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS peptides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, purpose TEXT, evidence_tier TEXT, notes TEXT
        )
    """)
    
    # Seed Base Exercises if empty
    cursor.execute("SELECT COUNT(*) FROM exercises")
    if cursor.fetchone()[0] == 0:
        wger_machines = [
            ("Barbell Bench Press", "Chest", "Barbell", "Compound chest press movement using an Olympic barbell."),
            ("Incline Dumbbell Press", "Chest", "Dumbbell", "Upper pectoral development on an inclined bench."),
            ("Pec Deck Machine", "Chest", "Machine", "Isolated chest fly using a selectorized mechanical cam."),
            ("Lat Pulldown Machine", "Back", "Machine", "Cable pulldown targeting latissimus dorsi with knee pads."),
            ("Seated Cable Row", "Back", "Cable", "Horizontal row utilizing a cable pulley and foot platform."),
            ("Leg Press Machine", "Legs", "Machine", "Sled-based lower body press for quadriceps and glutes."),
            ("Seated Leg Extension", "Legs", "Machine", "Isolated knee extension machine for rectus femoris."),
            ("Lying Leg Curl Machine", "Legs", "Machine", "Prone hamstring curl against a padded weighted lever."),
            ("Smith Machine Squat", "Legs", "Machine", "Guided vertical barbell squat for stable multi-joint loading."),
            ("Cable Lateral Raise", "Shoulders", "Cable", "Constant tension side delt isolation using a low cable pulley.")
        ]
        cursor.executemany("INSERT INTO exercises (title, category, equipment, description) VALUES (?, ?, ?, ?)", wger_machines)

    # Seed Base Peptides if empty
    cursor.execute("SELECT COUNT(*) FROM peptides")
    if cursor.fetchone()[0] == 0:
        sample_peptides = [
            ("BPC-157", "Tendon, Ligament & Joint Healing", "High Evidence (Animal/Pre-clinical)", "Widely studied for accelerating angiogenesis and healing of soft-tissue and connective tissue injuries."),
            ("TB-500 (Thymosin Beta-4)", "Systemic Tissue Repair & Anti-Inflammation", "Moderate Evidence", "Promotes endothelial cell migration, actin regulation, and systemic injury recovery."),
            ("CJC-1295 / Ipamorelin", "Growth Hormone Secretagogue (Fat Loss / Hypertrophy)", "Moderate Clinical Evidence", "GHRH and ghrelin receptor agonist stack used to pulse natural growth hormone production."),
            ("Tirzepatide / Semaglutide", "Appetite Regulation & Fat Loss", "High Clinical Evidence (FDA Approved)", "GLP-1/GIP receptor agonists with robust trial data demonstrating significant metabolic fat loss results.")
        ]
        cursor.executemany("INSERT INTO peptides (name, purpose, evidence_tier, notes) VALUES (?, ?, ?, ?)", sample_peptides)

    conn.commit()
    conn.close()

init_user_db()

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Apex Fitness & Nutrition Engine</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="bg-slate-950 text-slate-100 font-sans min-h-screen">

    <nav class="border-b border-slate-800 bg-slate-900/90 p-4 sticky top-0 z-40 flex flex-wrap justify-between items-center backdrop-blur gap-4">
        <div class="flex items-center gap-2">
            <div class="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center font-bold text-lg">A</div>
            <span class="font-bold text-xl text-blue-500 tracking-wider">APEX TRACKER</span>
        </div>
        <div class="flex flex-wrap gap-4 text-sm font-semibold">
            <button onclick="switchTab('home')" id="tab-home" class="text-blue-500 border-b-2 border-blue-500 pb-1">Home & Goals</button>
            <button onclick="switchTab('nutrition')" id="tab-nutrition" class="text-slate-400 hover:text-slate-200 pb-1">Nutrition Diary</button>
            <button onclick="switchTab('workout')" id="tab-workout" class="text-slate-400 hover:text-slate-200 pb-1">Workout</button>
            <button onclick="switchTab('supplements')" id="tab-supplements" class="text-slate-400 hover:text-slate-200 pb-1">Supplements</button>
            <button onclick="switchTab('peptides')" id="tab-peptides" class="text-slate-400 hover:text-slate-200 pb-1">Peptide Optimizer</button>
            <button onclick="switchTab('analytics')" id="tab-analytics" class="text-slate-400 hover:text-slate-200 pb-1">Analytics</button>
        </div>
    </nav>

    <main class="max-w-6xl mx-auto p-6 space-y-6">
        
        <!-- HOME / GOALS TAB -->
        <section id="sec-home" class="space-y-6">
            <div class="bg-slate-900 border border-slate-800 p-6 rounded-2xl space-y-6">
                <div>
                    <h1 class="text-2xl font-bold text-slate-100">Nutrition & Plan Configuration</h1>
                    <p class="text-sm text-slate-400">Generate an automated plan based on your metrics, or enter your own custom targets.</p>
                </div>

                <div class="flex gap-6 border-b border-slate-800 pb-4">
                    <label class="flex items-center gap-2 cursor-pointer text-sm font-bold"><input type="radio" name="plan_mode" value="auto" checked onchange="togglePlanMode()"> Auto-Generate (Profile & Datasets)</label>
                    <label class="flex items-center gap-2 cursor-pointer text-sm font-bold"><input type="radio" name="plan_mode" value="custom" onchange="togglePlanMode()"> Custom Manual Input</label>
                </div>

                <form id="profile-form" onsubmit="saveProfile(event)" class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div class="auto-field"><label class="block text-xs text-slate-400 mb-1">Current Body Weight (lbs)</label><input type="number" id="p-weight" value="170" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm"></div>
                    <div class="auto-field"><label class="block text-xs text-slate-400 mb-1">Primary Goal</label>
                        <select id="p-goal" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm"><option value="cut">Cutting (-500 kcal)</option><option value="maintain">Maintenance</option><option value="bulk">Bulking (+400 kcal)</option></select>
                    </div>
                    <div class="auto-field"><label class="block text-xs text-slate-400 mb-1">Diet Model Preset</label>
                        <select id="p-diet" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm"><option value="high_protein">High Protein Hypertrophy</option><option value="balanced" selected>Balanced Health</option><option value="low_carb">Low Carb / Keto</option></select>
                    </div>

                    <div class="custom-field hidden"><label class="block text-xs text-slate-400 mb-1">Target Calories</label><input type="number" id="c-cal" value="2500" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm"></div>
                    <div class="custom-field hidden"><label class="block text-xs text-slate-400 mb-1">Target Protein (g)</label><input type="number" id="c-pro" value="180" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm"></div>
                    <div class="custom-field hidden"><label class="block text-xs text-slate-400 mb-1">Target Carbs (g)</label><input type="number" id="c-carb" value="250" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm"></div>
                    <div class="custom-field hidden"><label class="block text-xs text-slate-400 mb-1">Target Fat (g)</label><input type="number" id="c-fat" value="70" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm"></div>
                    <div class="custom-field hidden"><label class="block text-xs text-slate-400 mb-1">Target Sugar (g)</label><input type="number" id="c-sug" value="50" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm"></div>
                    <div class="custom-field hidden"><label class="block text-xs text-slate-400 mb-1">Target Fiber (g)</label><input type="number" id="c-fib" value="30" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm"></div>

                    <div class="md:col-span-3 flex justify-end">
                        <button type="submit" class="bg-blue-600 hover:bg-blue-500 px-6 py-2.5 rounded-lg text-sm font-semibold transition">Save & Apply Targets</button>
                    </div>
                </form>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-6 gap-4 text-center">
                <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl"><span class="text-xs text-slate-400 block">Calories</span><span id="t-cal" class="text-xl font-bold text-slate-100">0</span></div>
                <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl"><span class="text-xs text-slate-400 block">Protein</span><span id="t-pro" class="text-xl font-bold text-blue-400">0g</span></div>
                <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl"><span class="text-xs text-slate-400 block">Carbs</span><span id="t-carb" class="text-xl font-bold text-amber-400">0g</span></div>
                <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl"><span class="text-xs text-slate-400 block">Fat</span><span id="t-fat" class="text-xl font-bold text-rose-400">0g</span></div>
                <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl"><span class="text-xs text-slate-400 block">Sugar Limit</span><span id="t-sug" class="text-xl font-bold text-pink-400">0g</span></div>
                <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl"><span class="text-xs text-slate-400 block">Fiber Goal</span><span id="t-fib" class="text-xl font-bold text-emerald-400">0g</span></div>
            </div>
        </section>

        <!-- NUTRITION DIARY TAB -->
        <section id="sec-nutrition" class="space-y-6 hidden">
            <div class="flex justify-between items-center">
                <h1 class="text-2xl font-bold">Nutrition Diary</h1>
                <button onclick="openFoodModal('Breakfast')" class="bg-blue-600 hover:bg-blue-500 text-xs px-4 py-2 rounded-lg font-bold">+ Log Food</button>
            </div>
            <div id="meal-diary" class="space-y-4"></div>
        </section>

        <!-- WORKOUT TAB -->
        <section id="sec-workout" class="space-y-6 hidden">
            <div class="flex justify-between items-center">
                <div>
                    <h1 class="text-2xl font-bold">Active Workout Session</h1>
                    <p class="text-xs text-slate-400">Wger Machine & Free Weight Database</p>
                </div>
                <button onclick="openExerciseModal()" class="bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded-lg text-xs font-bold">+ Add Machine / Exercise</button>
            </div>
            <div id="workout-session-container" class="space-y-4"></div>
        </section>

        <!-- SUPPLEMENTS TAB -->
        <section id="sec-supplements" class="space-y-6 hidden">
            <h1 class="text-2xl font-bold">Supplement Stack & Harvard Guidelines</h1>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-2xl space-y-4">
                    <h2 class="text-lg font-bold">My Daily Supplements</h2>
                    <div class="flex gap-2">
                        <input type="text" id="sup-input" placeholder="e.g., Creatine Monohydrate (5g)" class="flex-1 bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm">
                        <button onclick="logSupplement()" class="bg-blue-600 px-4 py-2 rounded text-sm font-bold">Log</button>
                    </div>
                    <ul id="sup-list" class="space-y-2 text-sm divide-y divide-slate-800"></ul>
                </div>
                <div class="bg-blue-950/20 border border-blue-900/50 p-6 rounded-2xl text-xs text-blue-100 space-y-3">
                    <h2 class="text-base font-bold text-blue-400">Evidence-Based Insights (Harvard Nutrition Source)</h2>
                    <p>Supplements are not strictly regulated for safety before sale; always consult a healthcare professional.</p>
                    <ul class="list-disc pl-4 space-y-2">
                        <li><strong>Protein:</strong> 1.4–2.0 g/kg daily optimizes muscle synthesis.</li>
                        <li><strong>Caffeine:</strong> Effective pre-workout stimulant, but pure powdered caffeine is toxic/lethal in high amounts.</li>
                        <li><strong>Beta-Alanine:</strong> Helps delay neuromuscular fatigue during intense sets.</li>
                    </ul>
                </div>
            </div>
        </section>

        <!-- PEPTIDE OPTIMIZER TAB -->
        <section id="sec-peptides" class="space-y-6 hidden">
            <div class="flex justify-between items-center">
                <div>
                    <h1 class="text-2xl font-bold">Peptide Optimizer & Evidence Matrix</h1>
                    <p class="text-xs text-slate-400">Evaluate efficacy, scientific consensus, and track your active peptide protocols.</p>
                </div>
                <button onclick="openPeptideModal()" class="bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded-lg text-xs font-bold">+ Track Custom Peptide</button>
            </div>

            <!-- Curated Evidence Matrix Grid -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6" id="peptide-matrix-container"></div>

            <!-- Active Peptide Stack Tracker -->
            <div class="bg-slate-900 border border-slate-800 p-6 rounded-2xl space-y-4">
                <h2 class="text-lg font-bold text-slate-100">My Active Peptide Stack</h2>
                <div id="active-peptide-stack" class="divide-y divide-slate-800 text-sm">
                    <p class="text-xs text-slate-500 italic py-2">No custom peptides tracked yet.</p>
                </div>
            </div>
        </section>

        <!-- ANALYTICS TAB -->
        <section id="sec-analytics" class="hidden"><p class="text-slate-400">Analytics loaded.</p></section>
    </main>

    <!-- FOOD SEARCH MODAL -->
    <div id="food-modal" class="fixed inset-0 bg-black/80 hidden z-50 flex items-center justify-center p-4">
        <div class="bg-slate-900 border border-slate-800 w-full max-w-xl rounded-2xl p-6 space-y-4">
            <div class="flex justify-between items-center"><h3 class="font-bold text-lg">Search & Add to <span id="modal-meal-name" class="text-blue-400"></span></h3><button onclick="closeFoodModal()">✕</button></div>
            <div class="flex gap-2">
                <input type="text" id="food-search-box" placeholder="Search USDA food..." class="flex-1 bg-slate-800 border rounded px-3 py-2 text-sm">
                <button onclick="searchFoodAPI()" class="bg-blue-600 px-4 py-2 rounded text-sm font-bold">Search</button>
            </div>
            <div id="food-search-results" class="max-h-60 overflow-y-auto divide-y divide-slate-800 text-sm"></div>
        </div>
    </div>

    <!-- EXERCISE SELECTOR MODAL -->
    <div id="exercise-modal" class="fixed inset-0 bg-black/80 hidden z-50 flex items-center justify-center p-4">
        <div class="bg-slate-900 border border-slate-800 w-full max-w-xl rounded-2xl p-6 space-y-4">
            <div class="flex justify-between items-center"><h3 class="font-bold text-lg">Select Machine / Exercise</h3><button onclick="closeExerciseModal()">✕</button></div>
            <input type="text" id="ex-search-box" onkeyup="loadExercises()" placeholder="Search 'Leg Press', 'Pec Deck', 'Cable'..." class="w-full bg-slate-800 border rounded px-3 py-2 text-sm">
            <div id="exercise-results-list" class="max-h-60 overflow-y-auto divide-y divide-slate-800 text-sm"></div>
        </div>
    </div>

    <!-- PEPTIDE TRACKER MODAL -->
    <div id="peptide-modal" class="fixed inset-0 bg-black/80 hidden z-50 flex items-center justify-center p-4">
        <div class="bg-slate-900 border border-slate-800 w-full max-w-md rounded-2xl p-6 space-y-4">
            <div class="flex justify-between items-center"><h3 class="font-bold text-lg">Track Peptide Protocol</h3><button onclick="closePeptideModal()">✕</button></div>
            <form onsubmit="submitPeptide(event)" class="space-y-3 text-xs">
                <div><label class="block text-slate-400 mb-1">Peptide Name</label><input type="text" id="pep-name" required placeholder="e.g., BPC-157" class="w-full bg-slate-800 border rounded px-3 py-2 text-sm"></div>
                <div><label class="block text-slate-400 mb-1">Target Purpose</label><input type="text" id="pep-purpose" required placeholder="e.g., Tendon Healing" class="w-full bg-slate-800 border rounded px-3 py-2 text-sm"></div>
                <div><label class="block text-slate-400 mb-1">Evidence Consensus / Tier</label><select id="pep-tier" class="w-full bg-slate-800 border rounded px-3 py-2 text-sm"><option value="High Evidence">High Evidence</option><option value="Moderate Evidence">Moderate Evidence</option><option value="Low / Anecdotal">Low / Anecdotal</option></select></div>
                <div><label class="block text-slate-400 mb-1">Notes / Dosage Protocol</label><textarea id="pep-notes" placeholder="e.g., 250mcg daily subq near site" class="w-full bg-slate-800 border rounded px-3 py-2 text-sm h-20"></textarea></div>
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-500 py-2 rounded font-bold mt-2">Add to Active Stack</button>
            </form>
        </div>
    </div>

    <script>
        let userTargets = { cal: 2500, pro: 170, carb: 250, fat: 70, sug: 50, fib: 30 };
        let activeMeal = 'Breakfast';
        let diaryLogs = { Breakfast: [], Lunch: [], Dinner: [], Snacks: [] };
        let activeWorkout = [];
        let supplements = [];
        let customPeptides = [];

        function switchTab(tab) {
            ['home', 'nutrition', 'workout', 'supplements', 'peptides', 'analytics'].forEach(t => {
                document.getElementById('sec-' + t).classList.add('hidden');
                document.getElementById('tab-' + t).className = "text-slate-400 hover:text-slate-200 pb-1";
            });
            document.getElementById('sec-' + tab).classList.remove('hidden');
            document.getElementById('tab-' + tab).className = "text-blue-500 border-b-2 border-blue-500 pb-1";
            if(tab === 'nutrition') renderDiary();
            if(tab === 'workout') renderWorkout();
            if(tab === 'peptides') loadPeptidesData();
        }

        function togglePlanMode() {
            const isCustom = document.querySelector('input[name="plan_mode"]:checked').value === 'custom';
            document.querySelectorAll('.auto-field').forEach(el => el.classList.toggle('hidden', isCustom));
            document.querySelectorAll('.custom-field').forEach(el => el.classList.toggle('hidden', !isCustom));
        }

        function saveProfile(e) {
            e.preventDefault();
            const mode = document.querySelector('input[name="plan_mode"]:checked').value;
            if(mode === 'custom') {
                userTargets.cal = parseFloat(document.getElementById('c-cal').value);
                userTargets.pro = parseFloat(document.getElementById('c-pro').value);
                userTargets.carb = parseFloat(document.getElementById('c-carb').value);
                userTargets.fat = parseFloat(document.getElementById('c-fat').value);
                userTargets.sug = parseFloat(document.getElementById('c-sug').value);
                userTargets.fib = parseFloat(document.getElementById('c-fib').value);
            } else {
                const w = parseFloat(document.getElementById('p-weight').value);
                userTargets.cal = Math.round(w * 15);
                userTargets.pro = Math.round(w * 1.1);
                userTargets.carb = Math.round((userTargets.cal * 0.45) / 4);
                userTargets.fat = Math.round((userTargets.cal * 0.25) / 9);
            }
            document.getElementById('t-cal').innerText = userTargets.cal;
            document.getElementById('t-pro').innerText = userTargets.pro + 'g';
            document.getElementById('t-carb').innerText = userTargets.carb + 'g';
            document.getElementById('t-fat').innerText = userTargets.fat + 'g';
            document.getElementById('t-sug').innerText = userTargets.sug + 'g';
            document.getElementById('t-fib').innerText = userTargets.fib + 'g';
            alert("Targets successfully updated!");
        }

        function openFoodModal(meal) { activeMeal = meal; document.getElementById('modal-meal-name').innerText = meal; document.getElementById('food-modal').classList.remove('hidden'); }
        function closeFoodModal() { document.getElementById('food-modal').classList.add('hidden'); }

        async function searchFoodAPI() {
            const q = document.getElementById('food-search-box').value;
            const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
            const data = await res.json();
            const div = document.getElementById('food-search-results');
            div.innerHTML = "";
            data.results.forEach(f => {
                div.innerHTML += `<div class="py-2 flex justify-between items-center">
                    <div><span class="font-bold block">${f.description}</span><span class="text-xs text-slate-400">100g • ${Math.round(f.calories)} kcal | P:${f.protein} C:${f.carbs} F:${f.fat}</span></div>
                    <button onclick="logFoodItem('${f.description.replace(/'/g, "\\'")}', ${f.calories}, ${f.protein}, ${f.carbs}, ${f.fat})" class="bg-blue-600 px-3 py-1 rounded text-xs">Add</button>
                </div>`;
            });
        }

        function logFoodItem(name, cal, pro, carb, fat) {
            diaryLogs[activeMeal].push({ name, cal: Math.round(cal), pro: Math.round(pro), carb: Math.round(carb), fat: Math.round(fat), sug: 0, fib: 0 });
            closeFoodModal();
            renderDiary();
        }

        function renderDiary() {
            const container = document.getElementById('meal-diary');
            container.innerHTML = "";
            ['Breakfast', 'Lunch', 'Dinner', 'Snacks'].forEach(m => {
                const items = diaryLogs[m];
                let html = `<div class="bg-slate-900 border border-slate-800 p-4 rounded-xl"><div class="flex justify-between border-b border-slate-800 pb-2 mb-2"><span class="font-bold">${m}</span><button onclick="openFoodModal('${m}')" class="text-xs text-blue-400 font-semibold">+ Add Food</button></div>`;
                items.forEach(i => {
                    html += `<div class="flex justify-between text-xs py-1"><span>${i.name}</span><span class="font-mono text-slate-400">${i.cal} kcal (P:${i.pro} C:${i.carb} F:${i.fat})</span></div>`;
                });
                if(items.length === 0) html += `<div class="text-xs text-slate-500 italic">No foods logged.</div>`;
                container.innerHTML += html + `</div>`;
            });
        }

        function openExerciseModal() { document.getElementById('exercise-modal').classList.remove('hidden'); loadExercises(); }
        function closeExerciseModal() { document.getElementById('exercise-modal').classList.add('hidden'); }

        async function loadExercises() {
            const q = document.getElementById('ex-search-box').value;
            const res = await fetch(`/api/exercises?q=${encodeURIComponent(q)}`);
            const data = await res.json();
            const div = document.getElementById('exercise-results-list');
            div.innerHTML = "";
            data.exercises.forEach(ex => {
                div.innerHTML += `<div class="py-2 flex justify-between items-center">
                    <div><span class="font-bold block">${ex.title}</span><span class="text-xs text-slate-400">${ex.equipment} • ${ex.category}</span></div>
                    <button onclick="addExerciseToWorkout('${ex.title.replace(/'/g, "\\'")}', '${ex.equipment}')" class="bg-blue-600 px-3 py-1 rounded text-xs font-bold">+ Add</button>
                </div>`;
            });
        }

        function addExerciseToWorkout(title, equipment) {
            activeWorkout.push({ title, equipment, sets: [{ weight: 135, reps: 10, completed: false }] });
            closeExerciseModal();
            renderWorkout();
        }

        function renderWorkout() {
            const container = document.getElementById('workout-session-container');
            container.innerHTML = "";
            activeWorkout.forEach((ex, exIdx) => {
                let html = `<div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-3">
                    <div class="flex justify-between items-center">
                        <div><h3 class="font-bold text-blue-400 text-base">${ex.title}</h3><span class="text-xs text-slate-400">${ex.equipment}</span></div>
                        <button onclick="addSet(${exIdx})" class="text-xs text-blue-400 font-bold">+ Add Set</button>
                    </div>
                    <div class="space-y-2">`;
                ex.sets.forEach((set, setIdx) => {
                    html += `<div class="flex items-center gap-3 text-xs bg-slate-950 p-2 rounded-xl border border-slate-800/80">
                        <span class="font-mono text-slate-500 w-6">Set ${setIdx+1}</span>
                        <input type="number" value="${set.weight}" onchange="updateSet(${exIdx}, ${setIdx}, 'weight', this.value)" placeholder="lbs" class="w-20 bg-slate-900 border border-slate-700 rounded p-1.5 text-center font-mono">
                        <input type="number" value="${set.reps}" onchange="updateSet(${exIdx}, ${setIdx}, 'reps', this.value)" placeholder="reps" class="w-16 bg-slate-900 border border-slate-700 rounded p-1.5 text-center font-mono">
                        <input type="checkbox" ${set.completed ? 'checked' : ''} onchange="toggleSet(${exIdx}, ${setIdx})" class="w-5 h-5 accent-emerald-500 ml-auto">
                    </div>`;
                });
                container.innerHTML += html + `</div></div>`;
            });
            if(activeWorkout.length === 0) container.innerHTML = `<div class="text-slate-500 text-sm italic p-4 text-center bg-slate-900 border border-slate-800 rounded-2xl">No exercises added yet. Click '+ Add Machine / Exercise' above.</div>`;
        }

        function addSet(exIdx) {
            const lastSet = activeWorkout[exIdx].sets[activeWorkout[exIdx].sets.length - 1] || { weight: 135, reps: 10 };
            activeWorkout[exIdx].sets.push({ weight: lastSet.weight, reps: lastSet.reps, completed: false });
            renderWorkout();
        }
        function updateSet(exIdx, setIdx, field, val) { activeWorkout[exIdx].sets[setIdx][field] = parseFloat(val) || 0; }
        function toggleSet(exIdx, setIdx) { activeWorkout[exIdx].sets[setIdx].completed = !activeWorkout[exIdx].sets[setIdx].completed; }

        function logSupplement() {
            const box = document.getElementById('sup-input');
            if(!box.value.trim()) return;
            supplements.push(box.value);
            box.value = '';
            renderSupplements();
        }
        function renderSupplements() {
            document.getElementById('sup-list').innerHTML = supplements.map(s => `<li class="py-2 flex justify-between"><span>${s}</span><span class="text-emerald-400 text-xs font-bold">✓ Logged</span></li>`).join('');
        }

        async function loadPeptidesData() {
            const res = await fetch('/api/peptides');
            const data = await res.json();
            const matrixDiv = document.getElementById('peptide-matrix-container');
            matrixDiv.innerHTML = "";
            
            data.peptides.forEach(p => {
                let badgeColor = "bg-amber-950 text-amber-300 border-amber-800";
                if(p.evidence_tier.includes("High")) badgeColor = "bg-emerald-950 text-emerald-300 border-emerald-800";
                
                matrixDiv.innerHTML += `
                    <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-3">
                        <div class="flex justify-between items-start">
                            <div>
                                <h3 class="font-bold text-base text-blue-400">${p.name}</h3>
                                <span class="text-xs text-slate-400">${p.purpose}</span>
                            </div>
                            <span class="text-[10px] font-mono px-2 py-0.5 rounded-full border ${badgeColor}">${p.evidence_tier}</span>
                        </div>
                        <p class="text-xs text-slate-300 leading-relaxed">${p.notes}</p>
                    </div>`;
            });
        }

        function openPeptideModal() { document.getElementById('peptide-modal').classList.remove('hidden'); }
        function closePeptideModal() { document.getElementById('peptide-modal').classList.add('hidden'); }

        async function submitPeptide(e) {
            e.preventDefault();
            const pep = {
                name: document.getElementById('pep-name').value,
                purpose: document.getElementById('pep-purpose').value,
                evidence_tier: document.getElementById('pep-tier').value,
                notes: document.getElementById('pep-notes').value
            };
            
            await fetch('/api/peptides', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(pep)
            });
            
            customPeptides.push(pep);
            renderActivePeptides();
            closePeptideModal();
            document.getElementById('pep-name').value = '';
            document.getElementById('pep-purpose').value = '';
            document.getElementById('pep-notes').value = '';
        }

        function renderActivePeptides() {
            const stackDiv = document.getElementById('active-peptide-stack');
            if(customPeptides.length === 0) {
                stackDiv.innerHTML = '<p class="text-xs text-slate-500 italic py-2">No custom peptides tracked yet.</p>';
                return;
            }
            stackDiv.innerHTML = "";
            customPeptides.forEach(cp => {
                stackDiv.innerHTML += `
                    <div class="py-2.5 flex justify-between items-center text-xs">
                        <div>
                            <span class="font-bold text-slate-200 block">${cp.name} (${cp.purpose})</span>
                            <span class="text-slate-400">${cp.notes || 'No protocol notes provided'}</span>
                        </div>
                        <span class="text-emerald-400 font-mono">Active Stack</span>
                    </div>`;
            });
        }

        window.onload = function() { saveProfile(new Event('submit')); };
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def read_index():
    return HTML_CONTENT

@app.get("/api/search")
def search_foods(q: str = Query(..., min_length=2)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    query = """
        SELECT f.fdc_id, f.description, 
               COALESCE(n.calories, 0) as calories,
               COALESCE(n.protein_g, 0) as protein,
               COALESN(n.carbs_g, 0) as carbs,
               COALESCE(n.fat_g, 0) as fat,
               0 as sugar, 0 as sat_fat, 0 as fiber
        FROM foods f
        LEFT JOIN nutrients n ON f.fdc_id = n.fdc_id
        WHERE f.description LIKE ? LIMIT 20
    """
    try:
        cursor.execute(query, (f"%{q}%",))
        rows = cursor.fetchall()
    except:
        rows = []
    conn.close()
    return {"results": [dict(row) for row in rows]}

@app.get("/api/exercises")
def get_exercises(q: str = Query("")):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM exercises WHERE title LIKE ? OR category LIKE ? OR equipment LIKE ?", (f"%{q}%", f"%{q}%", f"%{q}%"))
    rows = cursor.fetchall()
    conn.close()
    return {"exercises": [dict(r) for r in rows]}

@app.get("/api/peptides")
def get_peptides():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM peptides")
    rows = cursor.fetchall()
    conn.close()
    return {"peptides": [dict(r) for r in rows]}

@app.post("/api/peptides")
def add_peptide(p: dict = Body(...)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO peptides (name, purpose, evidence_tier, notes)
        VALUES (:name, :purpose, :evidence_tier, :notes)
    """, p)
    conn.commit()
    conn.close()
    return {"status": "success"}

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)