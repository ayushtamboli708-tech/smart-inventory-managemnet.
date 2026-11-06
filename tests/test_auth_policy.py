from __future__ import annotations

import pytest

from core.auth import (
    User,
    assert_company,
    authenticate_staff_pin,
    can,
    hash_password,
    is_legacy_plaintext,
    plaintext_login_enabled,
    require_owner,
    require_role,
    staff_pin_configured,
    verify_password,
)
from core.errors import PermissionDenied, ValidationError
from services.catalog import create_product
from services.sales import refund_sale
from services.users import create_user

OWNER = User(user_id=1, company_id=1, username="owner", role="Owner")
STAFF = User(user_id=2, company_id=1, username="cashier", role="Staff")


def test_owner_passes_owner_policy() -> None:
    assert require_owner(OWNER) is OWNER


def test_staff_is_denied_owner_policy() -> None:
    with pytest.raises(PermissionDenied):
        require_owner(STAFF)


def test_missing_user_is_denied() -> None:
    with pytest.raises(PermissionDenied):
        require_role(None, "Owner")


def test_can_checks_roles() -> None:
    assert can(OWNER, "Owner")
    assert can(STAFF, "Staff")
    assert not can(STAFF, "Owner")
    assert not can(None, "Staff")


def test_company_boundary() -> None:
    with pytest.raises(PermissionDenied):
        assert_company(OWNER, 2)
    assert_company(OWNER, 1)


def test_password_hash_round_trip() -> None:
    hashed = hash_password("ChangeMe123!")
    assert hashed.startswith("$2")
    assert verify_password("ChangeMe123!", hashed)
    assert not verify_password("wrong", hashed)


def test_plaintext_passwords_never_authenticate_by_default(monkeypatch) -> None:
    monkeypatch.delenv("STOCKWISE_ALLOW_PLAINTEXT", raising=False)
    assert is_legacy_plaintext("admin123")
    assert not plaintext_login_enabled()
    assert not verify_password("admin123", "admin123")


def test_plaintext_login_requires_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("STOCKWISE_ALLOW_PLAINTEXT", "1")
    assert plaintext_login_enabled()


def test_usernames_are_restricted_to_a_safe_charset() -> None:
    with pytest.raises(ValidationError):
        create_user(
            None,
            1,
            OWNER,
            username="<script>alert(1)</script>",
            password="longenough",
            role="Staff",
        )


def test_staff_pin_fails_closed_without_configuration() -> None:
    assert not staff_pin_configured(None)
    assert not staff_pin_configured("")
    assert not authenticate_staff_pin("1234", None)
    assert not authenticate_staff_pin("1234", "")


def test_staff_pin_matches_only_when_configured() -> None:
    assert staff_pin_configured("1234")
    assert authenticate_staff_pin("1234", "1234")
    assert not authenticate_staff_pin("0000", "1234")


def test_catalog_write_rejects_staff_before_touching_the_database() -> None:
    with pytest.raises(PermissionDenied):
        create_product(
            None,
            1,
            STAFF,
            sku="SKU-1",
            name="Test",
            category="Other",
            unit="Pc",
            selling_price=1,
            reorder_threshold=1,
        )


def test_refund_rejects_staff_before_touching_the_database() -> None:
    with pytest.raises(PermissionDenied):
        refund_sale(None, 1, STAFF, 1)
