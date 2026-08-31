from __future__ import annotations


def test_list_organizations_only_active_memberships(client, make_user, make_organization, make_membership, login_as):
    user = make_user()
    active_org = make_organization(name="Active Org")
    invited_org = make_organization(name="Invited Org")
    make_membership(active_org, user, role_key="owner", status="active")
    make_membership(invited_org, user, role_key="member", status="invited")

    response = login_as(user).get("/api/v1/organizations")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["organization_id"] == str(active_org.id)
    assert data[0]["role_key"] == "owner"


def test_list_organizations_excludes_other_users(client, make_user, make_organization, make_membership, login_as):
    user_a = make_user()
    user_b = make_user()
    org_a = make_organization(name="Org A")
    org_b = make_organization(name="Org B")
    make_membership(org_a, user_a, role_key="owner")
    make_membership(org_b, user_b, role_key="owner")

    response = login_as(user_a).get("/api/v1/organizations")

    slugs = [row["slug"] for row in response.json()]
    assert org_a.slug in slugs
    assert org_b.slug not in slugs


def test_list_organizations_requires_authentication(client):
    response = client.get("/api/v1/organizations")
    assert response.status_code == 401
