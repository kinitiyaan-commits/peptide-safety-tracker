"""API-level smoke tests for the FastAPI server, including isolation over HTTP."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import peptide_safety.server as server


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    server.DB_PATH = tmp_path / "api_smoke.db"
    server.seeded_user_id = None  # force reseed against the test DB
    with TestClient(server.app) as client:
        yield client
    server.seeded_user_id = None


def test_index_serves_ui_with_disclaimer(client):
    html = client.get("/").text
    assert "PEPTIDE SAFETY TRACKER" in html
    assert "not medical advice" in html
    assert "never rates" in html


def test_demo_seed_via_startup(client):
    users = client.get("/api/users").json()["users"]
    assert len(users) == 1 and users[0]["is_demo"] == 1
    demo_id = users[0]["id"]
    usage = client.get(f"/api/usage/{demo_id}").json()["usage"]
    assert usage and all(u["unit"] in ("mcg", "mg", "IU", "units", "mL")
                         for u in usage)
    catalog = client.get("/api/catalog").json()["catalog"]
    assert catalog and all(c["source_url"].startswith("https://") for c in catalog)


def test_api_user_isolation(client):
    uid_a = client.post("/api/users", json={"display_name": "A"}).json()["user_id"]
    uid_b = client.post("/api/users", json={"display_name": "B"}).json()["user_id"]

    r = client.post(f"/api/usage/{uid_a}",
                    json={"peptide_name": "BPC-157", "amount": 250, "unit": "mcg"})
    assert r.status_code == 200
    r = client.post(f"/api/symptoms/{uid_a}",
                    json={"peptide_name": "BPC-157", "severity": 2,
                          "description": "A private note"})
    assert r.status_code == 200
    r = client.post(f"/api/reminders/{uid_a}",
                    json={"peptide_name": "BPC-157", "time_of_day": "09:00",
                          "days": "Daily"})
    assert r.status_code == 200

    # B sees nothing of A's data
    assert client.get(f"/api/usage/{uid_b}").json()["usage"] == []
    assert client.get(f"/api/symptoms/{uid_b}").json()["symptoms"] == []
    assert client.get(f"/api/reminders/{uid_b}").json()["reminders"] == []

    export_b = client.get(f"/api/export/{uid_b}?fmt=json").text
    assert "A private note" not in export_b
    assert "BPC-157" not in export_b


def test_api_rejects_unitless_and_bad_reminder(client):
    uid = client.post("/api/users", json={"display_name": "C"}).json()["user_id"]
    r = client.post(f"/api/usage/{uid}",
                    json={"peptide_name": "BPC-157", "amount": 250, "unit": ""})
    assert r.status_code == 400
    assert "unit must be one of" in r.json()["detail"]

    r = client.post(f"/api/reminders/{uid}",
                    json={"peptide_name": "BPC-157", "time_of_day": "25:00",
                          "days": "Daily"})
    assert r.status_code == 400


def test_api_cross_user_delete_denied(client):
    uid_a = client.post("/api/users", json={"display_name": "A2"}).json()["user_id"]
    uid_b = client.post("/api/users", json={"display_name": "B2"}).json()["user_id"]
    entry = client.post(f"/api/usage/{uid_a}",
                        json={"peptide_name": "BPC-157", "amount": 1, "unit": "mg"}
                        ).json()["entry_id"]
    assert client.delete(f"/api/usage/{uid_b}/{entry}").status_code == 404
    assert client.get(f"/api/usage/{uid_a}").json()["usage"]


def test_api_saved_products_flow(client):
    uid_a = client.post("/api/users", json={"display_name": "PA"}).json()["user_id"]
    uid_b = client.post("/api/users", json={"display_name": "PB"}).json()["user_id"]

    r = client.post(f"/api/products/{uid_a}",
                    json={"name": "BPC-157", "default_unit": "mcg"})
    assert r.status_code == 200
    r = client.post(f"/api/products/{uid_a}",
                    json={"name": "BPC-157", "default_unit": "mcg"})
    assert r.status_code == 400 and "already saved" in r.json()["detail"]
    r = client.post(f"/api/products/{uid_a}",
                    json={"name": "Bad", "default_unit": "grams"})
    assert r.status_code == 400

    names_a = [p["name"] for p in client.get(f"/api/products/{uid_a}").json()["products"]]
    names_b = [p["name"] for p in client.get(f"/api/products/{uid_b}").json()["products"]]
    assert names_a == ["BPC-157"] and names_b == []

    pid = client.get(f"/api/products/{uid_a}").json()["products"][0]["id"]
    assert client.delete(f"/api/products/{uid_b}/{pid}").status_code == 404
    assert client.delete(f"/api/products/{uid_a}/{pid}").status_code == 200


def test_verify_endpoint_is_link_out_only(client):
    data = client.get("/api/verify", params={"name": "Semaglutide"}).json()
    assert data["links"]["dailymed_label_search"].startswith("https://dailymed.nlm.nih.gov/")
    assert "not interpret" in data["links"]["disclaimer"]


class TestGoalsAPI:
    def test_registry_and_roundtrip_over_http(self, client):
        reg = client.get("/api/goals/registry").json()["goals"]
        assert "sleep" in reg and "height" in reg
        assert "field" in reg["sleep"] or "fields" in reg["sleep"]
        uid = client.post("/api/users", json={"display_name": "G1"}).json()["user_id"]
        r = client.put(f"/api/goals/{uid}", json={"goals": ["sleep", "height"]})
        assert r.status_code == 200
        assert client.get(f"/api/goals/{uid}").json()["goals"] == ["sleep", "height"]
        r = client.put(f"/api/goals/{uid}", json={"goals": ["bogus"]})
        assert r.status_code == 400

    def test_goal_data_over_http_and_isolation(self, client):
        uid_a = client.post("/api/users", json={"display_name": "GA"}).json()["user_id"]
        uid_b = client.post("/api/users", json={"display_name": "GB"}).json()["user_id"]
        client.put(f"/api/goals/{uid_a}", json={"goals": ["sleep"]})
        r = client.post(f"/api/usage/{uid_a}",
                        json={"peptide_name": "BPC-157", "amount": 1, "unit": "mg",
                              "goal_data": {"sleep_rating": 5}})
        assert r.status_code == 200
        rows_a = client.get(f"/api/usage/{uid_a}").json()["usage"]
        assert rows_a[0]["goal_data"] == {"sleep_rating": 5}
        rows_b = client.get(f"/api/usage/{uid_b}").json()["usage"]
        assert rows_b == []
        # B cannot log with A's goal fields
        r = client.post(f"/api/usage/{uid_b}",
                        json={"peptide_name": "X", "amount": 1, "unit": "mg",
                              "goal_data": {"sleep_rating": 3}})
        assert r.status_code == 400

    def test_catalog_endpoint_includes_metadata(self, client):
        catalog = client.get("/api/catalog").json()["catalog"]
        entry = next(c for c in catalog if "Somatropin" in c["name"])
        assert entry["review_status"] == "verified"
        assert any(c["review_status"] == "awaiting-verification" for c in catalog)




# --- moved from test_peptide_safety.py (needs the client fixture) ---
    def test_duplicate_over_http_409_then_override(self, client):
        uid = client.post("/api/users", json={"display_name": "Dup"}).json()["user_id"]
        body = {"peptide_name": "BPC-157", "amount": 1, "unit": "mg"}
        assert client.post(f"/api/usage/{uid}", json=body).status_code == 200
        r = client.post(f"/api/usage/{uid}", json=body)
        assert r.status_code == 409
        assert "duplicate" in r.json()["detail"].lower()
        body["override_duplicate"] = True
        assert client.post(f"/api/usage/{uid}", json=body).status_code == 200
        assert len(client.get(f"/api/usage/{uid}").json()["usage"]) == 2

    def test_observations_over_http(self, client):
        uid = client.post("/api/users", json={"display_name": "Obs"}).json()["user_id"]
        client.put(f"/api/goals/{uid}", json={"goals": ["sleep"]})
        r = client.post(f"/api/observations/{uid}",
                        json={"goal_data": {"sleep_rating": 2}})
        assert r.status_code == 200
        rows = client.get(f"/api/observations/{uid}").json()["observations"]
        assert rows[0]["goal_data"] == {"sleep_rating": 2}
        assert client.get(f"/api/usage/{uid}").json()["usage"] == []
        # other user cannot read or write it
        other = client.post("/api/users", json={"display_name": "Obs2"}).json()["user_id"]
        assert client.get(f"/api/observations/{other}").json()["observations"] == []
        assert client.post(f"/api/observations/{other}",
                           json={"goal_data": {"sleep_rating": 2}}).status_code == 400
        # delete scoped
        assert client.delete(f"/api/observations/{uid}/{rows[0]['id']}").status_code == 200
        assert client.get(f"/api/observations/{uid}").json()["observations"] == []

    def test_custom_text_over_http(self, client):
        uid = client.post("/api/users", json={"display_name": "Cust"}).json()["user_id"]
        r = client.put(f"/api/goals/{uid}",
                       json={"goals": ["custom"],
                             "custom_texts": {"custom": "<script>alert(1)</script>"}})
        assert r.status_code == 200
        details = client.get(f"/api/goals/{uid}").json()["details"]
        assert details[0]["custom_text"] == "<script>alert(1)</script>"  # stored raw, rendered escaped by UI


# --- moved from test_peptide_safety.py (needs the client fixture) ---
    def test_edit_over_http(self, client):
        uid = client.post("/api/users", json={"display_name": "Ed"}).json()["user_id"]
        eid = client.post(f"/api/usage/{uid}",
                          json={"peptide_name": "BPC-157", "amount": 1, "unit": "mg"}
                          ).json()["entry_id"]
        r = client.patch(f"/api/usage/{uid}/{eid}",
                         json={"amount": 2, "notes": "fixed"})
        assert r.status_code == 200 and r.json()["changed"] is True
        row = client.get(f"/api/usage/{uid}").json()["usage"][0]
        assert row["amount"] == 2 and row["corrections"][0]["previous"]["amount"] == 1
        # other user cannot PATCH it
        other = client.post("/api/users", json={"display_name": "Ed2"}).json()["user_id"]
        r2 = client.patch(f"/api/usage/{other}/{eid}", json={"notes": "hijack"})
        assert r2.status_code == 400
        # invalid edit → 400
        assert client.patch(f"/api/usage/{uid}/{eid}",
                            json={"unit": "cups"}).status_code == 400

    def test_same_key_replays_without_new_event(self, client):
        uid = client.post("/api/users", json={"display_name": "Idem"}).json()["user_id"]
        body = {"peptide_name": "BPC-157", "amount": 1, "unit": "mg",
                "idempotency_key": "abc-123"}
        r1 = client.post(f"/api/usage/{uid}", json=body)
        assert r1.status_code == 200 and r1.json()["replayed"] is False
        r2 = client.post(f"/api/usage/{uid}", json=body)
        assert r2.status_code == 200
        assert r2.json()["replayed"] is True
        assert r2.json()["entry_id"] == r1.json()["entry_id"]
        assert len(client.get(f"/api/usage/{uid}").json()["usage"]) == 1

    def test_retry_does_not_trigger_duplicate_guard(self, client):
        uid = client.post("/api/users", json={"display_name": "Idem2"}).json()["user_id"]
        body = {"peptide_name": "BPC-157", "amount": 1, "unit": "mg",
                "idempotency_key": "retry-key"}
        client.post(f"/api/usage/{uid}", json=body)
        # identical payload replay must NOT be a 409 duplicate prompt
        assert client.post(f"/api/usage/{uid}", json=body).status_code == 200

    def test_no_key_still_creates_and_duplicate_guard_still_applies(self, client):
        uid = client.post("/api/users", json={"display_name": "Idem3"}).json()["user_id"]
        body = {"peptide_name": "BPC-157", "amount": 1, "unit": "mg"}
        assert client.post(f"/api/usage/{uid}", json=body).status_code == 200
        r = client.post(f"/api/usage/{uid}", json=body)
        assert r.status_code == 409  # duplicate guard untouched by idempotency

    def test_keys_scoped_per_user(self, client):
        a = client.post("/api/users", json={"display_name": "IdemA"}).json()["user_id"]
        b = client.post("/api/users", json={"display_name": "IdemB"}).json()["user_id"]
        body = {"peptide_name": "BPC-157", "amount": 1, "unit": "mg",
                "idempotency_key": "shared-key"}
        r1 = client.post(f"/api/usage/{a}", json=body)
        r2 = client.post(f"/api/usage/{b}", json=body)
        # user B's submission with the same key is a NEW event, not a replay
        assert r1.json()["replayed"] is False and r2.json()["replayed"] is False
        assert r1.json()["entry_id"] != r2.json()["entry_id"]
        assert len(client.get(f"/api/usage/{b}").json()["usage"]) == 1

    def test_observation_idempotency(self, client):
        uid = client.post("/api/users", json={"display_name": "IdemO"}).json()["user_id"]
        client.put(f"/api/goals/{uid}", json={"goals": ["sleep"]})
        body = {"goal_data": {"sleep_rating": 3}, "idempotency_key": "obs-1"}
        r1 = client.post(f"/api/observations/{uid}", json=body)
        r2 = client.post(f"/api/observations/{uid}", json=body)
        assert r1.json()["replayed"] is False and r2.json()["replayed"] is True
        assert len(client.get(f"/api/observations/{uid}").json()["observations"]) == 1
