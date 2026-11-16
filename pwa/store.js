/* store.js — IndexedDB storage layer for the static PWA.
 *
 * ALL user data lives in the browser on this device. Nothing is ever sent
 * to a server. Clearing the browser's site data deletes every record.
 *
 * Stores (all records carry profileId; reads are always profile-scoped):
 *   profiles       {id, name, age?, trackingNote?, createdAt, consentAck}
 *   usage          {id, profileId, peptideName, amount, unit, route?, takenAt, notes, goalData?, corrections[]}
 *   symptoms       {id, profileId, peptideName, severity(1-5), description, loggedAt}
 *   observations   {id, profileId, takenAt, notes, goalData?, corrections[]}
 *   reminders      {id, profileId, peptideName, timeOfDay, days, notes, enabled}
 *   goals          {profileId, goalKeys[], customText?}   (one per profile)
 *   meta           {key, value}                            (e.g. active profile)
 */

const DB_NAME = "peptide-safety-tracker";
const DB_VERSION = 1;

const STORES = ["profiles", "usage", "symptoms", "observations",
                "reminders", "goals", "meta"];

let _dbPromise = null;

function openDB() {
  if (_dbPromise) return _dbPromise;
  _dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      for (const name of STORES) {
        if (!db.objectStoreNames.contains(name)) {
          const os = db.createObjectStore(name, { keyPath: "id" });
          if (name !== "profiles" && name !== "goals" && name !== "meta") {
            os.createIndex("profileId", "profileId", { unique: false });
          }
        }
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return _dbPromise;
}

function tx(store, mode, fn) {
  return openDB().then(db => new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const os = t.objectStore(store);
    let result;
    try { result = fn(os); } catch (e) { reject(e); return; }
    t.oncomplete = () => resolve(result && result._done !== undefined
      ? result._done : result);
    t.onerror = () => reject(t.error);
    t.onabort = () => reject(t.error);
  }));
}

function req(request, transform) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(transform ? transform(request.result) : request.result);
    request.onerror = () => reject(request.error);
  });
}

const Store = {
  // ---- generic ----
  getAll(store) {
    return tx(store, "readonly", os => req(os.getAll()));
  },
  get(store, id) {
    return tx(store, "readonly", os => req(os.get(id)));
  },
  put(store, record) {
    return tx(store, "readwrite", os => req(os.put(record)));
  },
  delete(store, id) {
    return tx(store, "readwrite", os => req(os.delete(id)));
  },
  clear(store) {
    return tx(store, "readwrite", os => req(os.clear()));
  },
  count(store) {
    return tx(store, "readonly", os => req(os.count()));
  },

  // ---- profiles ----
  async profiles() { return this.getAll("profiles"); },
  async createProfile(name, age, trackingNote) {
    const profile = {
      id: "p_" + crypto.randomUUID(),
      name: String(name).trim(),
      age: age == null || age === "" ? null : Number(age),
      trackingNote: trackingNote || "",
      consentAck: false,
      createdAt: new Date().toISOString(),
    };
    await this.put("profiles", profile);
    return profile;
  },
  async deleteProfile(profileId) {
    // cascade: every owned record is removed with the profile
    const owned = [["usage"], ["symptoms"], ["observations"], ["reminders"]];
    for (const [store] of owned) {
      const rows = (await this.getAll(store)).filter(r => r.profileId === profileId);
      for (const r of rows) await this.delete(store, r.id);
    }
    await this.delete("goals", profileId);
    return this.delete("profiles", profileId);
  },

  // ---- profile-scoped records ----
  async byProfile(store, profileId) {
    const rows = await this.getAll(store);
    return rows.filter(r => r.profileId === profileId)
               .sort((a, b) => String(b.takenAt || b.loggedAt || "")
                     .localeCompare(String(a.takenAt || a.loggedAt || "")));
  },
  async goalsFor(profileId) {
    return (await this.get("goals", profileId)) || { id: profileId, goalKeys: [] };
  },
  async setGoals(profileId, goalKeys) {
    return this.put("goals", { id: profileId, goalKeys });
  },

  // ---- meta ----
  async getMeta(key) {
    const row = await this.get("meta", key);
    return row ? row.value : null;
  },
  async setMeta(key, value) {
    return this.put("meta", { id: key, value });
  },

  // ---- import ----
  async wipeAllData() {
    for (const store of STORES) await this.clear(store);
  },
};

Store.STORES = STORES;
Store.DB_NAME = DB_NAME;
