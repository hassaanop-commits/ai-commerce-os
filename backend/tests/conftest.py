import os

# Must run before any `app.*` import, since app.core.config.settings is a
# module-level singleton read from the environment at first import. Pointing
# this at a dedicated test database (never the dev one) before anything else
# happens is what keeps tests from touching real data.
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/ai_commerce_os_test"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai.providers import get_default_ai_provider, get_default_image_provider
from app.ai.providers.mock_provider import MockProvider
from app.core.config import settings
from app.core.csrf import CSRF_HEADER_NAME, generate_csrf_token
from app.core.rate_limit import reset_auth_rate_limits
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Marketplace,
    MarketplaceConnection,
    Organization,
    OrganizationMember,
    Product,
    ProductAsset,
    Role,
    User,
)
from app.services.email import ConsoleEmailService, get_email_service
from app.services.sessions import create_session
from app.services.storage import LocalStorageProvider, get_storage_service


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(settings.database_url)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture(scope="session", autouse=True)
def _seed_roles(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    if session.query(Role).count() == 0:
        session.add_all(
            [
                Role(key="owner", name="Owner", rank=1),
                Role(key="admin", name="Admin", rank=2),
                Role(key="member", name="Member", rank=3),
            ]
        )
        session.commit()
    session.close()


@pytest.fixture(autouse=True)
def _reset_auth_rate_limits():
    # The limiter is a module-level singleton (see app.core.rate_limit) so
    # its state persists across tests unless cleared. TestClient always
    # connects as the same "testclient" host, so without this every test
    # after the first ~10 auth requests in the whole suite would start
    # tripping the rate limit regardless of which test it's in.
    reset_auth_rate_limits()
    yield
    reset_auth_rate_limits()


@pytest.fixture(autouse=True)
def _no_real_ai_retry_sleep(monkeypatch):
    # The AI retry loop (app.ai.tools._common.start_and_call) calls
    # time.sleep() between attempts. Every existing "__fail__"-sentinel test
    # across the suite raises category "provider_error", which is now
    # retryable -- without this, those tests would suddenly incur several
    # real seconds of backoff sleep each. Applied globally and autouse so no
    # test anywhere has to remember to fake this itself; a test that needs
    # to inspect the actual sleep calls/args can still install its own
    # monkeypatch on top from within the test body (applied later, so it
    # wins for that test).
    monkeypatch.setattr("app.ai.tools._common.time.sleep", lambda seconds: None)


@pytest.fixture(scope="session", autouse=True)
def _seed_marketplaces(engine):
    # Mirrors the real 658bd447c01e migration -- the test DB's schema comes
    # from Base.metadata.create_all(), not from running migrations, so this
    # data-only seed has to be reproduced here the same way _seed_roles
    # reproduces a448ddd85754.
    Session = sessionmaker(bind=engine)
    session = Session()
    if session.query(Marketplace).count() == 0:
        session.add(Marketplace(key="manual", name="Manual (test)", is_active=True))
        session.commit()
    session.close()


@pytest.fixture()
def db(engine):
    connection = engine.connect()
    outer_transaction = connection.begin()
    Session = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    session = Session()
    yield session
    session.close()
    outer_transaction.rollback()
    connection.close()


_email_counter = 0


@pytest.fixture()
def make_user(db):
    def _make(email: str | None = None, password_hash: str = "unused", full_name: str = "Test User", status: str = "active"):
        global _email_counter
        _email_counter += 1
        user = User(
            email=email or f"user{_email_counter}@example.com",
            hashed_password=password_hash,
            full_name=full_name,
            status=status,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


_slug_counter = 0


@pytest.fixture()
def make_organization(db):
    def _make(name: str = "Acme", slug: str | None = None):
        global _slug_counter
        _slug_counter += 1
        org = Organization(name=name, slug=slug or f"acme-{_slug_counter}")
        db.add(org)
        db.commit()
        db.refresh(org)
        return org

    return _make


@pytest.fixture()
def email_service():
    # A fresh ConsoleEmailService per test, so sent_emails from one test never
    # leaks into another via the module-level default singleton.
    return ConsoleEmailService()


@pytest.fixture()
def storage_service(tmp_path):
    # A fresh, isolated on-disk root per test -- never the real dev
    # var/storage/ directory -- so uploads from one test can't leak into or
    # collide with another's.
    return LocalStorageProvider(root=tmp_path / "storage")


@pytest.fixture()
def ai_provider():
    # MockProvider makes zero real network calls -- every test that goes
    # through the `client` fixture gets this instead of a real AI provider.
    return MockProvider()


@pytest.fixture()
def image_provider():
    # Same MockProvider, resolved independently -- text and image
    # generation are separate provider seams (get_default_ai_provider vs.
    # get_default_image_provider), both overridden here so no test ever
    # needs a real OpenAI/Anthropic key.
    return MockProvider()


@pytest.fixture()
def client(db, email_service, storage_service, ai_provider, image_provider):
    # Overriding get_db to always hand out this test's own savepoint-wrapped
    # session means every request in the test -- however many separate HTTP
    # calls that is -- shares one transaction, so it rolls back with everything
    # else at teardown instead of writing real rows to the test database.
    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_email_service] = lambda: email_service
    app.dependency_overrides[get_storage_service] = lambda: storage_service
    app.dependency_overrides[get_default_ai_provider] = lambda: ai_provider
    app.dependency_overrides[get_default_image_provider] = lambda: image_provider
    with TestClient(app) as test_client:
        # Mirrors what a real frontend does: read the (non-httpOnly) CSRF
        # cookie and echo it back as a header on every mutating request. This
        # makes CSRF transparent to tests that aren't specifically exercising
        # CSRF behavior -- pass skip_csrf=True to a request to bypass it and
        # test the missing-header case explicitly.
        original_request = test_client.request

        def _request_with_csrf(method, url, **kwargs):
            skip_csrf = kwargs.pop("skip_csrf", False)
            if not skip_csrf and method.upper() not in ("GET", "HEAD", "OPTIONS"):
                token = test_client.cookies.get(settings.csrf_cookie_name)
                if token:
                    headers = dict(kwargs.get("headers") or {})
                    headers.setdefault(CSRF_HEADER_NAME, token)
                    kwargs["headers"] = headers
            return original_request(method, url, **kwargs)

        test_client.request = _request_with_csrf
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def login_as(client, db):
    def _login_as(user: User):
        _, raw_token = create_session(db, user)
        client.cookies.set(settings.session_cookie_name, raw_token)
        client.cookies.set(settings.csrf_cookie_name, generate_csrf_token())
        return client

    return _login_as


@pytest.fixture()
def make_membership(db):
    def _make(organization: Organization, user: User, role_key: str = "member", status: str = "active"):
        role = db.query(Role).filter(Role.key == role_key).one()
        membership = OrganizationMember(
            organization_id=organization.id,
            user_id=user.id,
            role_id=role.id,
            status=status,
        )
        db.add(membership)
        db.commit()
        db.refresh(membership)
        return membership

    return _make


_sku_counter = 0


@pytest.fixture()
def make_product(db):
    def _make(organization: Organization, sku: str | None = None, title: str = "Test Product", **kwargs):
        global _sku_counter
        _sku_counter += 1
        product = Product(
            organization_id=organization.id,
            sku=sku or f"SKU-{_sku_counter}",
            title=title,
            **kwargs,
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return product

    return _make


_asset_counter = 0


@pytest.fixture()
def make_primary_asset(db):
    # Bypasses the upload API entirely -- for listing tests that just need
    # "a product with an eligible primary asset" set up quickly, not the
    # upload flow itself (already covered by test_product_assets_api.py).
    def _make(product: Product) -> ProductAsset:
        global _asset_counter
        _asset_counter += 1
        asset = ProductAsset(
            organization_id=product.organization_id,
            product_id=product.id,
            source="upload",
            asset_type="image",
            storage_key=f"test/{product.id}/{_asset_counter}.jpg",
            url=f"/api/v1/organizations/{product.organization_id}/products/{product.id}/assets/asset-{_asset_counter}/file",
            status="ready",
            approval_status="not_required",
            is_primary=True,
            position=1,
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset

    return _make


@pytest.fixture()
def make_marketplace_connection(db):
    def _make(
        organization: Organization,
        marketplace_key: str = "manual",
        display_name: str | None = None,
        status: str = "connected",
    ) -> MarketplaceConnection:
        marketplace = db.query(Marketplace).filter(Marketplace.key == marketplace_key).one()
        connection = MarketplaceConnection(
            organization_id=organization.id,
            marketplace_id=marketplace.id,
            display_name=display_name,
            credentials_ciphertext=None,
            status=status,
        )
        db.add(connection)
        db.commit()
        db.refresh(connection)
        return connection

    return _make


# Minimal valid-magic-bytes JPEG content -- enough to pass sniff_image_content_type,
# small enough to be a fast, deterministic fixture (no real image library needed for tests).
FAKE_JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 128
