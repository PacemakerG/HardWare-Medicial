import pytest


def test_auth_me_default_anonymous(test_client):
    res = test_client.get("/api/v1/auth/me")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["logged_in"] is False
    assert data["user_id"] == "anonymous"


def test_auth_login_and_logout(test_client):
    login = test_client.post(
        "/api/v1/auth/login",
        json={"user_id": "doctor_zhang", "tenant_id": "hospital_a"},
    )
    assert login.status_code == 200
    payload = login.json()
    assert payload["logged_in"] is True
    assert payload["user_id"] == "doctor_zhang"
    assert payload["tenant_id"] == "hospital_a"

    me = test_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    me_data = me.json()
    assert me_data["logged_in"] is True
    assert me_data["user_id"] == "doctor_zhang"
    assert me_data["tenant_id"] == "hospital_a"

    logout = test_client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    assert logout.json()["logged_in"] is False

    me_after = test_client.get("/api/v1/auth/me")
    assert me_after.status_code == 200
    assert me_after.json()["logged_in"] is False
