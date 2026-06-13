"""
test_security.py – Test suite for sandboxing, authentication, and permission levels.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Ensure hub root is on sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
_HUB_ROOT = os.path.dirname(_HERE)
if _HUB_ROOT not in sys.path:
    sys.path.insert(0, _HUB_ROOT)

from mcp_hub.config import settings, Settings
from mcp_hub.auth import verify_token, AuthError
from mcp_hub.permissions import (
    load_default_permissions,
    load_token_permissions,
    assert_permission,
    check_permission,
    PermLevel,
    grant_token_permission,
)
from mcp_hub.sandbox import validate_path, check_file_size, trim_rows, SandboxError


class TestSandbox(unittest.TestCase):
    def setUp(self):
        # Configure ALLOWED_PATHS to a mock temporary location
        self.test_root = Path(_HERE).resolve()
        settings.allowed_paths = str(self.test_root)

    def test_valid_path(self):
        # Path inside test_root should be resolved and pass validation
        resolved = validate_path(str(self.test_root / "test_security.py"), must_exist=True)
        self.assertEqual(resolved, (self.test_root / "test_security.py").resolve())

    def test_path_traversal_escaped(self):
        # Escaping sandbox root using relative path traversal should raise PermissionError
        outside_path = str(self.test_root / ".." / ".." / "main.py")
        with self.assertRaises(PermissionError):
            validate_path(outside_path)

    def test_null_byte_rejected(self):
        # Null bytes should raise SandboxError
        with self.assertRaises(SandboxError):
            validate_path("some_file\x00.txt")

    def test_windows_reserved_device_rejected(self):
        # Windows reserved names anywhere in the path should raise SandboxError
        with self.assertRaises(SandboxError):
            validate_path(str(self.test_root / "CON.txt"))
        with self.assertRaises(SandboxError):
            validate_path(str(self.test_root / "nul"))
        with self.assertRaises(SandboxError):
            validate_path(str(self.test_root / "subfolder" / "COM3" / "file.txt"))


class TestAuthenticationAndPermissions(unittest.TestCase):
    def setUp(self):
        settings.auth_enabled = True
        settings.auth_tokens = "secret123:execute,read_only_token:read"
        
        # Override get_auth_tokens to match runtime implementation
        def get_auth_tokens_mocked(self_obj) -> set[str]:
            tokens = set()
            for t in self_obj.auth_tokens.split(","):
                t = t.strip()
                if not t:
                    continue
                if ":" in t:
                    t = t.split(":", 1)[0].strip()
                tokens.add(t)
            return tokens
        
        # Monkeypatch the method for tests
        self.original_get_auth_tokens = Settings.get_auth_tokens
        Settings.get_auth_tokens = get_auth_tokens_mocked

        load_default_permissions()
        load_token_permissions()

    def tearDown(self):
        Settings.get_auth_tokens = self.original_get_auth_tokens

    def test_verify_token(self):
        self.assertTrue(verify_token("secret123"))
        self.assertTrue(verify_token("read_only_token"))
        self.assertFalse(verify_token("invalid_token"))
        self.assertFalse(verify_token(""))

    def test_permission_enforcement(self):
        # read_file needs READ level
        self.assertTrue(check_permission("read_only_token", "read_file"))
        self.assertTrue(check_permission("secret123", "read_file"))
        
        # git_commit needs EXECUTE level (so read_only_token should be rejected)
        self.assertFalse(check_permission("read_only_token", "git_commit"))
        self.assertTrue(check_permission("secret123", "git_commit"))

        # Non-existent or empty tokens should have NONE permission
        self.assertFalse(check_permission("invalid_token", "read_file"))
        self.assertFalse(check_permission("", "read_file"))


if __name__ == "__main__":
    unittest.main()
