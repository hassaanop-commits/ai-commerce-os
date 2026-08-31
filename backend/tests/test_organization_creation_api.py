from __future__ import annotations

SIGNUP_PASSWORD = "a-very-strong-password-123"


def _signed_up_client(client, email="org.creator@example.com"):
    resp = client.post(
        "/api/v1/auth/signup", json={"email": email, "password": SIGNUP_PASSWORD, "full_name": "Org Creator"}
    )
    assert resp.status_code == 201
    return client


def test_authenticated_organization_creation(client):
    _signed_up_client(client)

    response = client.post("/api/v1/organizations", json={"name": "Second Org"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Second Org"
    assert body["slug"]


def test_unauthenticated_organization_creation_rejected(client):
    response = client.post("/api/v1/organizations", json={"name": "Nope"})
    assert response.status_code == 401


def test_unique_slug_generated_for_duplicate_names(client):
    _signed_up_client(client)

    first = client.post("/api/v1/organizations", json={"name": "Duplicate Name"})
    second = client.post("/api/v1/organizations", json={"name": "Duplicate Name"})

    assert first.status_code == second.status_code == 201
    assert first.json()["slug"] != second.json()["slug"]


def test_creator_becomes_owner(client):
    _signed_up_client(client, email="owner.creates@example.com")

    create_resp = client.post("/api/v1/organizations", json={"name": "Owned Org"})
    org_id = create_resp.json()["id"]

    orgs_resp = client.get("/api/v1/organizations")
    matching = [o for o in orgs_resp.json() if o["organization_id"] == org_id]

    assert len(matching) == 1
    assert matching[0]["role_key"] == "owner"
