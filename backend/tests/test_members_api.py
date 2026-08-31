from __future__ import annotations


def test_list_members(make_user, make_organization, make_membership, login_as):
    owner = make_user(email="members.owner@example.com")
    member = make_user(email="members.member@example.com")
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    make_membership(org, member, role_key="member")

    response = login_as(owner).get(f"/api/v1/organizations/{org.id}/members")

    assert response.status_code == 200
    emails = {m["email"] for m in response.json()}
    assert emails == {"members.owner@example.com", "members.member@example.com"}


def test_admin_can_change_member_role(make_user, make_organization, make_membership, login_as):
    owner = make_user(email="role.owner@example.com")
    admin = make_user(email="role.admin@example.com")
    member = make_user(email="role.member@example.com")
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    make_membership(org, admin, role_key="admin")
    member_membership = make_membership(org, member, role_key="member")

    response = login_as(admin).patch(
        f"/api/v1/organizations/{org.id}/members/{member_membership.id}", json={"role_key": "admin"}
    )

    assert response.status_code == 200
    assert response.json()["role_key"] == "admin"


def test_admin_cannot_promote_to_owner(make_user, make_organization, make_membership, login_as):
    owner = make_user(email="promote.owner@example.com")
    admin = make_user(email="promote.admin@example.com")
    member = make_user(email="promote.member@example.com")
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    make_membership(org, admin, role_key="admin")
    member_membership = make_membership(org, member, role_key="member")

    response = login_as(admin).patch(
        f"/api/v1/organizations/{org.id}/members/{member_membership.id}", json={"role_key": "owner"}
    )

    assert response.status_code == 403


def test_admin_cannot_demote_owner(make_user, make_organization, make_membership, login_as):
    owner_a = make_user(email="demote.owner.a@example.com")
    owner_b = make_user(email="demote.owner.b@example.com")
    admin = make_user(email="demote.admin@example.com")
    org = make_organization()
    make_membership(org, owner_a, role_key="owner")
    owner_b_membership = make_membership(org, owner_b, role_key="owner")
    make_membership(org, admin, role_key="admin")

    response = login_as(admin).patch(
        f"/api/v1/organizations/{org.id}/members/{owner_b_membership.id}", json={"role_key": "admin"}
    )

    assert response.status_code == 403


def test_owner_can_demote_another_owner_if_not_last(make_user, make_organization, make_membership, login_as):
    owner_a = make_user(email="valid.demote.a@example.com")
    owner_b = make_user(email="valid.demote.b@example.com")
    org = make_organization()
    make_membership(org, owner_a, role_key="owner")
    owner_b_membership = make_membership(org, owner_b, role_key="owner")

    response = login_as(owner_a).patch(
        f"/api/v1/organizations/{org.id}/members/{owner_b_membership.id}", json={"role_key": "admin"}
    )

    assert response.status_code == 200
    assert response.json()["role_key"] == "admin"


def test_cannot_demote_last_owner(make_user, make_organization, make_membership, login_as):
    owner = make_user(email="last.owner@example.com")
    org = make_organization()
    owner_membership = make_membership(org, owner, role_key="owner")

    response = login_as(owner).patch(
        f"/api/v1/organizations/{org.id}/members/{owner_membership.id}", json={"role_key": "admin"}
    )

    assert response.status_code == 409


def test_admin_can_remove_member(make_user, make_organization, make_membership, login_as):
    owner = make_user(email="remove.owner@example.com")
    admin = make_user(email="remove.admin@example.com")
    member = make_user(email="remove.member@example.com")
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    make_membership(org, admin, role_key="admin")
    member_membership = make_membership(org, member, role_key="member")

    response = login_as(admin).delete(f"/api/v1/organizations/{org.id}/members/{member_membership.id}")

    assert response.status_code == 204


def test_admin_cannot_remove_owner(make_user, make_organization, make_membership, login_as):
    owner = make_user(email="noremove.owner@example.com")
    admin = make_user(email="noremove.admin@example.com")
    org = make_organization()
    owner_membership = make_membership(org, owner, role_key="owner")
    make_membership(org, admin, role_key="admin")

    response = login_as(admin).delete(f"/api/v1/organizations/{org.id}/members/{owner_membership.id}")

    assert response.status_code == 403


def test_cannot_remove_last_owner(make_user, make_organization, make_membership, login_as):
    owner = make_user(email="last.remove.owner@example.com")
    org = make_organization()
    owner_membership = make_membership(org, owner, role_key="owner")

    response = login_as(owner).delete(f"/api/v1/organizations/{org.id}/members/{owner_membership.id}")

    assert response.status_code == 409


def test_cross_organization_member_access_rejected(make_user, make_organization, make_membership, login_as):
    owner_a = make_user(email="cross.owner.a@example.com")
    owner_b = make_user(email="cross.owner.b@example.com")
    org_a = make_organization()
    org_b = make_organization()
    make_membership(org_a, owner_a, role_key="owner")
    make_membership(org_b, owner_b, role_key="owner")

    response = login_as(owner_a).get(f"/api/v1/organizations/{org_b.id}/members")

    assert response.status_code == 403
