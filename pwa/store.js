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
 *   vials          {id, profileId, peptideName, mixedOn?, discardOn?, notes?}
 *   goals          {profileId, goalKeys[], customText?}   (one per profile)
 *   meta           {key, value}                            (e.g. active profile)
 */

const DB_NAME = "peptide-safety-tracker";
// v2 adds "productUnits" (remembered last-confirmed unit per product).
// v3 adds "vials" (user-entered supply log: mix date + discard date).
// The upgrade path below only CREATES missing stores — it never deletes or
// clears anything, so records from any previous release survive updates.
const DB_VERSION = 3;

const STORES = ["profiles", "usage", "symptoms", "observations",
                "reminders", "goals", "meta", "productUnits", "vials"];

let _dbPromise = null;

// Open at an explicit version (the normal path), or — if the database has
// already been upgraded beyond DB_VERSION (e.g. after rolling back the
// app code, or a newer tab upgraded it) — fall back to opening whatever
// version currently exists instead of failing with VersionError. Upgrade
// handling is additive only, so it is safe at any version.
function openDBVersioned(version) {
  return new Promise((resolve, reject) => {
    const req = version === undefined
      ? indexedDB.open(DB_NAME) : indexedDB.open(DB_NAME, version);
    req.onupgradeneeded = () => {
      const db = req.result;
      // Data-preserving upgrade: create any store this release needs that an
      // older installation is missing. Never delete or clear existing stores
      // here — a tester's records must survive every update.
      for (const name of STORES) {
        if (!db.objectStoreNames.contains(name)) {
          const os = db.createObjectStore(name, { keyPath: "id" });
          if (name !== "profiles" && name !== "goals" && name !== "meta" &&
              name !== "productUnits") {
            os.createIndex("profileId", "profileId", { unique: false });
          }
        }
      }
    };
    req.onblocked = () => {
      // Another tab still holds an old-version connection, so this tab's
      // upgrade cannot proceed yet. Surface it instead of hanging silently;
      // the request may still succeed later, and then we close immediately
      // so we never become the blocker ourselves.
      _dbPromise = null;
      req.onsuccess = () => req.result.close();
      if (typeof Store !== "undefined" && Store.onBlocked) {
        Store.onBlocked(new Error(
          "blocked: close this app in other tabs or windows, then reload here to continue the update"));
      }
      reject(new Error(
        "blocked: close this app in other tabs or windows, then reload here to continue the update"));
    };
    req.onsuccess = () => {
      const db = req.result;
      // If a NEWER version of the app (another tab running newer code)
      // requests an upgrade, this connection must close so it can proceed.
      // Dropping _dbPromise makes the next call reopen at the new version.
      db.onversionchange = () => {
        db.close();
        _dbPromise = null;
      };
      resolve(db);
    };
    req.onerror = () => reject(req.error);
  });
}

function openDB() {
  if (_dbPromise) return _dbPromise;
  _dbPromise = openDBVersioned(DB_VERSION).catch(err => {
    if (err && err.name === "VersionError") {
      // The database is at a NEWER version than this code declares
      // (possible after a code rollback). Records still open fine at the
      // existing version — extra stores are simply ignored by this code.
      _dbPromise = null;
      return openDBVersioned(undefined);
    }
    _dbPromise = null;
    throw err;
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
  // Set by app.js: called when a DB upgrade is blocked by another open tab,
  // so the UI can tell the user what to do instead of failing silently.
  onBlocked: null,

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
    const owned = [["usage"], ["symptoms"], ["observations"], ["reminders"],
                   ["vials"]];
    for (const [store] of owned) {
      const rows = (await this.getAll(store)).filter(r => r.profileId === profileId);
      for (const r of rows) await this.delete(store, r.id);
    }
    await this.delete("goals", profileId);
    // also drop remembered units for this profile's products
    const units = (await this.getAll("productUnits"))
      .filter(u => u.profileId === profileId);
    for (const u of units) await this.delete("productUnits", u.id);
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

  // ---- remembered product units (last confirmed unit per product) ----
  // Keyed by "profileId|lowercase name" so the same product in a different
  // profile never inherits another profile's unit.
  async rememberedUnit(profileId, name) {
    const row = await this.get("productUnits",
                               profileId + "|" + String(name).toLowerCase());
    return row ? row.unit : null;
  },
  async rememberUnit(profileId, name, unit) {
    return this.put("productUnits", {
      id: profileId + "|" + String(name).toLowerCase(),
      profileId, unit, name: String(name),
    });
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

  // ---- atomic multi-store import ----
  // All writes land in ONE IndexedDB transaction across all affected
  // stores: either every record is written or none is. If anything fails
  // or the transaction aborts, existing data is untouched. No awaits are
  // allowed between the requests — they are queued synchronously.
  //   writes: [{store, records: [..]}]   (all stores must already exist)
  //   clearStores: store names emptied first (inside the same transaction)
  importAtomic(writes, clearStores) {
    return openDB().then(db => new Promise((resolve, reject) => {
      const names = [...new Set(writes.map(w => w.store)
        .concat(clearStores || []))];
      let t;
      try { t = db.transaction(names, "readwrite"); }
      catch (e) { reject(e); return; }
      t.oncomplete = () => resolve(true);
      t.onerror = () => reject(t.error);
      t.onabort = () => reject(t.error ||
        new Error("Import aborted — nothing was changed"));
      try {
        for (const name of clearStores || []) t.objectStore(name).clear();
        for (const w of writes) {
          const os = t.objectStore(w.store);
          for (const r of w.records) os.put(r);
        }
      } catch (e) {
        try { t.abort(); } catch (_) {}
        reject(e);
      }
    }));
  },
};

Store.STORES = STORES;
Store.DB_NAME = DB_NAME;
