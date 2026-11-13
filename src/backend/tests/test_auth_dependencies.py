"""Kiểm tra xác thực và phân quyền, không gọi Supabase hoặc DB thật."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.core import auth
from app.models.enum import UserRole, UserStatus


@pytest.fixture
def auth_context(monkeypatch):
    db = Mock()
    user = SimpleNamespace(
        user_id="22222222-2222-2222-2222-222222222222",
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
    )
    db.query.return_value.filter.return_value.first.return_value = user
    supabase = Mock()
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id=user.user_id)
    )
    monkeypatch.setattr(auth, "supabase", supabase)
    app = FastAPI()
    app.dependency_overrides[auth.get_db] = lambda: db

    @app.get("/optional")
    def optional(user=Depends(auth.get_optional_user)):
        return {"user_id": str(user.user_id) if user else None}

    @app.get("/required")
    def required(user=Depends(auth.get_current_user)):
        return {"user_id": str(user.user_id)}

    @app.get("/admin")
    def admin(user=Depends(auth.require_admin)):
        return {"user_id": str(user.user_id)}

    return TestClient(app), supabase, db, user


@pytest.mark.parametrize("header", [None, "Basic abc", "Bearer"])
def test_missing_or_malformed_token(auth_context, header):
    client, supabase, db, _ = auth_context
    headers = {"Authorization": header} if header else {}
    assert client.get("/optional", headers=headers).json() == {"user_id": None}
    assert client.get("/required", headers=headers).status_code == 401
    supabase.auth.get_user.assert_not_called()
    db.query.assert_not_called()


def test_valid_token_returns_database_profile(auth_context):
    client, supabase, _, user = auth_context
    response = client.get("/required", headers={"Authorization": "Bearer valid"})
    assert response.status_code == 200
    assert response.json() == {"user_id": user.user_id}
    supabase.auth.get_user.assert_called_once_with("valid")


def test_invalid_token_allows_guest_but_rejects_required(auth_context):
    client, supabase, _, _ = auth_context
    supabase.auth.get_user.return_value = SimpleNamespace(user=None)
    headers = {"Authorization": "Bearer invalid"}
    assert client.get("/optional", headers=headers).json() == {"user_id": None}
    assert client.get("/required", headers=headers).status_code == 401


def test_auth_api_error_is_treated_as_invalid_token(auth_context):
    _, supabase, db, _ = auth_context
    supabase.auth.get_user.side_effect = auth.AuthApiError(
        "invalid token", 401, "bad_jwt"
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid")
    assert auth.get_optional_user(credentials, db) is None
    db.query.assert_not_called()


@pytest.mark.parametrize("endpoint", ["/optional", "/required"])
def test_auth_service_failure_returns_503(auth_context, endpoint):
    client, supabase, _, _ = auth_context
    supabase.auth.get_user.side_effect = RuntimeError("service unavailable")
    response = client.get(endpoint, headers={"Authorization": "Bearer valid"})
    assert response.status_code == 503


def test_missing_profile_is_forbidden(auth_context):
    client, _, db, _ = auth_context
    db.query.return_value.filter.return_value.first.return_value = None
    response = client.get("/required", headers={"Authorization": "Bearer valid"})
    assert response.status_code == 403


def test_admin_requires_active_admin_profile(auth_context):
    client, _, _, user = auth_context
    headers = {"Authorization": "Bearer valid"}
    assert client.get("/admin", headers=headers).status_code == 403
    user.role = UserRole.ADMIN
    assert client.get("/admin", headers=headers).status_code == 200
    user.status = None
    assert client.get("/admin", headers=headers).status_code == 403
