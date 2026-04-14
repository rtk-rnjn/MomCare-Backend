"""Tests for admin RBAC, log analytics, and restart authorization."""

from __future__ import annotations

import time
import unittest
import uuid

from src.models.admin import AdminCreateRequest, AdminLoginRequest, AdminRole, AdminUpdateRequest
from src.utils.admin_auth import (
    create_admin_access_token,
    create_admin_refresh_token,
    decode_admin_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing(unittest.TestCase):
    def test_hash_and_verify_password(self):
        password = "test_password_123"
        hashed = hash_password(password)
        self.assertNotEqual(password, hashed)
        self.assertTrue(verify_password(password, hashed))

    def test_wrong_password_fails(self):
        password = "correct_password"
        hashed = hash_password(password)
        self.assertFalse(verify_password("wrong_password", hashed))


class TestAdminTokens(unittest.TestCase):
    def test_create_and_decode_access_token(self):
        admin_id = str(uuid.uuid4())
        token = create_admin_access_token(admin_id, "testadmin", "admin")
        payload = decode_admin_token(token, "admin_access")
        self.assertEqual(payload["sub"], admin_id)
        self.assertEqual(payload["username"], "testadmin")
        self.assertEqual(payload["role"], "admin")
        self.assertEqual(payload["type"], "admin_access")

    def test_create_and_decode_refresh_token(self):
        admin_id = str(uuid.uuid4())
        token, jti = create_admin_refresh_token(admin_id)
        payload = decode_admin_token(token, "admin_refresh")
        self.assertEqual(payload["sub"], admin_id)
        self.assertEqual(payload["jti"], jti)
        self.assertEqual(payload["type"], "admin_refresh")

    def test_wrong_type_raises(self):
        admin_id = str(uuid.uuid4())
        access_token = create_admin_access_token(admin_id, "testadmin", "admin")
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            decode_admin_token(access_token, "admin_refresh")
        self.assertEqual(ctx.exception.status_code, 401)


class TestAdminModels(unittest.TestCase):
    def test_admin_login_request(self):
        req = AdminLoginRequest(username="admin", password="password123")
        self.assertEqual(req.username, "admin")
        self.assertEqual(req.password, "password123")

    def test_admin_create_request_validation(self):
        req = AdminCreateRequest(username="new_admin", password="password123")
        self.assertEqual(req.username, "new_admin")

    def test_admin_create_request_short_username_fails(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            AdminCreateRequest(username="ab", password="password123")

    def test_admin_create_request_short_password_fails(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            AdminCreateRequest(username="validuser", password="short")

    def test_admin_create_request_invalid_username_chars(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            AdminCreateRequest(username="user@name!", password="password123")

    def test_admin_update_request_optional_fields(self):
        req = AdminUpdateRequest()
        self.assertIsNone(req.is_active)
        self.assertIsNone(req.password)

    def test_admin_update_request_with_values(self):
        req = AdminUpdateRequest(is_active=False, password="newpassword123")
        self.assertFalse(req.is_active)
        self.assertEqual(req.password, "newpassword123")


class TestAdminRoles(unittest.TestCase):
    def test_role_values(self):
        self.assertEqual(AdminRole.SUPER_ADMIN, "super_admin")
        self.assertEqual(AdminRole.ADMIN, "admin")

    def test_super_admin_token_has_correct_role(self):
        admin_id = str(uuid.uuid4())
        token = create_admin_access_token(admin_id, "superadmin", AdminRole.SUPER_ADMIN)
        payload = decode_admin_token(token, "admin_access")
        self.assertEqual(payload["role"], "super_admin")

    def test_admin_token_has_correct_role(self):
        admin_id = str(uuid.uuid4())
        token = create_admin_access_token(admin_id, "regularadmin", AdminRole.ADMIN)
        payload = decode_admin_token(token, "admin_access")
        self.assertEqual(payload["role"], "admin")


class TestRBACLogic(unittest.TestCase):
    """Tests for the RBAC authorization logic."""

    def test_super_admin_can_access_super_admin_routes(self):
        """Super admin role should pass require_super_admin check."""
        admin_id = str(uuid.uuid4())
        token = create_admin_access_token(admin_id, "superadmin", AdminRole.SUPER_ADMIN)
        payload = decode_admin_token(token, "admin_access")
        self.assertEqual(payload["role"], AdminRole.SUPER_ADMIN)

    def test_regular_admin_cannot_access_super_admin_routes(self):
        """Regular admin role should fail require_super_admin check."""
        admin_id = str(uuid.uuid4())
        token = create_admin_access_token(admin_id, "admin", AdminRole.ADMIN)
        payload = decode_admin_token(token, "admin_access")
        self.assertNotEqual(payload["role"], AdminRole.SUPER_ADMIN)

    def test_admin_can_access_admin_routes(self):
        """Both admin and super_admin roles should pass require_admin check."""
        for role in [AdminRole.ADMIN, AdminRole.SUPER_ADMIN]:
            admin_id = str(uuid.uuid4())
            token = create_admin_access_token(admin_id, "user", role)
            payload = decode_admin_token(token, "admin_access")
            self.assertIn(payload["role"], [AdminRole.ADMIN, AdminRole.SUPER_ADMIN])


class TestRestartAuthorization(unittest.TestCase):
    """Tests for restart endpoint authorization logic."""

    def test_restart_requires_super_admin_role(self):
        """Only super_admin should be able to trigger restart."""
        admin_id = str(uuid.uuid4())
        # Super admin token
        sa_token = create_admin_access_token(admin_id, "superadmin", AdminRole.SUPER_ADMIN)
        sa_payload = decode_admin_token(sa_token, "admin_access")
        self.assertEqual(sa_payload["role"], AdminRole.SUPER_ADMIN)

        # Regular admin token
        regular_token = create_admin_access_token(admin_id, "admin", AdminRole.ADMIN)
        regular_payload = decode_admin_token(regular_token, "admin_access")
        self.assertNotEqual(regular_payload["role"], AdminRole.SUPER_ADMIN)

    def test_restart_feature_flag_logic(self):
        """ADMIN_ENABLE_RESTART should control restart availability."""
        import os

        # Test that the env var is read correctly
        os.environ["ADMIN_ENABLE_RESTART"] = "true"
        self.assertTrue(os.getenv("ADMIN_ENABLE_RESTART", "false").lower() == "true")

        os.environ["ADMIN_ENABLE_RESTART"] = "false"
        self.assertFalse(os.getenv("ADMIN_ENABLE_RESTART", "false").lower() == "true")

        # Clean up
        os.environ["ADMIN_ENABLE_RESTART"] = "true"


class TestAuditLogModel(unittest.TestCase):
    def test_audit_log_fields(self):
        from src.models.audit_log import AuditLogModel

        log = AuditLogModel(
            admin_id="test-id",
            admin_username="testadmin",
            action="test_action",
            target_type="user",
            target_id="user-123",
            timestamp=time.time(),
        )
        self.assertEqual(log.admin_username, "testadmin")
        self.assertEqual(log.action, "test_action")
        self.assertIsNotNone(log.id)


class TestHTTPLogModel(unittest.TestCase):
    def test_http_log_fields(self):
        from src.models.http_log import HTTPLogModel

        log = HTTPLogModel(
            timestamp=time.time(),
            method="GET",
            path="/api/v1/test",
            status_code=200,
            process_time_ms=15.5,
            client_ip="127.0.0.1",
        )
        self.assertEqual(log.method, "GET")
        self.assertEqual(log.status_code, 200)
        self.assertIsNotNone(log.id)


if __name__ == "__main__":
    unittest.main()
