"""S4.1 — JWKS RS256 PyJWKClient bounded kid + iss/aud/role + HS256 allowlist."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest


def _rsa_pair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key()
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    pub_pem = pub.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv_pem, pub_pem


class TestJwksRs256Verifier:
    def test_rs256_valid_token_verifies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import jwt as pyjwt

        priv_pem, pub_pem = _rsa_pair()
        from bot.config import _verify_jwt_rs256

        iss, aud = "https://proj.supabase.co/auth/v1", "authenticated"
        monkeypatch.setenv("SUPABASE_JWKS_URL", "https://proj.supabase.co/auth/v1/.well-known/jwks.json")
        monkeypatch.setenv("SUPABASE_JWT_ISSUER", iss)
        monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", aud)
        token = pyjwt.encode(
            {"role": "service_role", "iss": iss, "aud": aud, "exp": int(time.time()) + 600},
            priv_pem,
            algorithm="RS256",
            headers={"kid": "k1"},
        )
        mk, mc = MagicMock(), MagicMock()
        mk.key = pub_pem
        mc.get_signing_key_from_jwt.return_value = mk
        with patch("jwt.PyJWKClient", return_value=mc):
            assert _verify_jwt_rs256(token) == "service_role"

    def test_rs256_invalid_signature_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import jwt as pyjwt
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        _, pub_pem = _rsa_pair()
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode()
        monkeypatch.setenv("SUPABASE_JWKS_URL", "https://proj.supabase.co/auth/v1/.well-known/jwks.json")
        monkeypatch.setenv("SUPABASE_JWT_ISSUER", "https://proj.supabase.co/auth/v1")
        monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
        token = pyjwt.encode(
            {
                "role": "service_role",
                "iss": "https://proj.supabase.co/auth/v1",
                "aud": "authenticated",
                "exp": int(time.time()) + 600,
            },
            other_pem,
            algorithm="RS256",
            headers={"kid": "k1"},
        )
        mk, mc = MagicMock(), MagicMock()
        mk.key = pub_pem
        mc.get_signing_key_from_jwt.return_value = mk
        from bot.config import _verify_jwt_rs256

        with patch("jwt.PyJWKClient", return_value=mc):
            assert _verify_jwt_rs256(token) is None

    def test_rs256_kid_refresh_once_then_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import jwt as pyjwt

        priv_pem, pub_pem = _rsa_pair()
        monkeypatch.setenv("SUPABASE_JWKS_URL", "https://proj.supabase.co/auth/v1/.well-known/jwks.json")
        monkeypatch.setenv("SUPABASE_JWT_ISSUER", "https://proj.supabase.co/auth/v1")
        monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
        token = pyjwt.encode(
            {
                "role": "service_role",
                "iss": "https://proj.supabase.co/auth/v1",
                "aud": "authenticated",
                "exp": int(time.time()) + 600,
            },
            priv_pem,
            algorithm="RS256",
            headers={"kid": "rot"},
        )
        from bot.config import _verify_jwt_rs256

        fail = MagicMock()
        fail.get_signing_key_from_jwt.side_effect = pyjwt.exceptions.PyJWKClientError("kid not found")
        ok_key, ok = MagicMock(), MagicMock()
        ok_key.key = pub_pem
        ok.get_signing_key_from_jwt.return_value = ok_key
        with patch("jwt.PyJWKClient", side_effect=[fail, ok]):
            assert _verify_jwt_rs256(token) == "service_role"

    def test_rs256_kid_refresh_bounded_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import jwt as pyjwt

        priv_pem, _ = _rsa_pair()
        monkeypatch.setenv("SUPABASE_JWKS_URL", "https://proj.supabase.co/auth/v1/.well-known/jwks.json")
        monkeypatch.setenv("SUPABASE_JWT_ISSUER", "https://proj.supabase.co/auth/v1")
        monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
        token = pyjwt.encode(
            {
                "role": "service_role",
                "iss": "https://proj.supabase.co/auth/v1",
                "aud": "authenticated",
                "exp": int(time.time()) + 600,
            },
            priv_pem,
            algorithm="RS256",
            headers={"kid": "unk"},
        )
        from bot.config import _verify_jwt_rs256

        mc = MagicMock()
        mc.get_signing_key_from_jwt.side_effect = pyjwt.exceptions.PyJWKClientError("kid not found")
        with patch("jwt.PyJWKClient", return_value=mc):
            assert _verify_jwt_rs256(token) is None
            assert mc.get_signing_key_from_jwt.call_count <= 2

    @pytest.mark.parametrize("missing", ["iss", "aud", "exp", "role"])
    def test_rs256_missing_claims_fail(self, monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
        import jwt as pyjwt

        priv_pem, pub_pem = _rsa_pair()
        monkeypatch.setenv("SUPABASE_JWKS_URL", "https://proj.supabase.co/auth/v1/.well-known/jwks.json")
        monkeypatch.setenv("SUPABASE_JWT_ISSUER", "https://proj.supabase.co/auth/v1")
        monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
        base = {
            "role": "service_role",
            "iss": "https://proj.supabase.co/auth/v1",
            "aud": "authenticated",
            "exp": int(time.time()) + 600,
        }
        base.pop(missing)
        token = pyjwt.encode(base, priv_pem, algorithm="RS256", headers={"kid": "k1"})
        from bot.config import _verify_jwt_rs256

        mk, mc = MagicMock(), MagicMock()
        mk.key = pub_pem
        mc.get_signing_key_from_jwt.return_value = mk
        with patch("jwt.PyJWKClient", return_value=mc):
            assert _verify_jwt_rs256(token) is None

    def test_hs256_confusion_blocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import jwt as pyjwt

        priv_pem, pub_pem = _rsa_pair()
        monkeypatch.setenv("SUPABASE_JWKS_URL", "https://proj.supabase.co/auth/v1/.well-known/jwks.json")
        monkeypatch.setenv("SUPABASE_JWT_ISSUER", "https://proj.supabase.co/auth/v1")
        monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
        payload = {
            "role": "service_role",
            "iss": "https://proj.supabase.co/auth/v1",
            "aud": "authenticated",
            "exp": int(time.time()) + 600,
        }
        rs_token = pyjwt.encode(payload, priv_pem, algorithm="RS256", headers={"kid": "k1"})
        monkeypatch.setenv("SUPABASE_JWT_SECRET", "strong-secret-32bytes-for-hs256-test")
        from bot.config import _verify_jwt_rs256, _verify_jwt_signature

        assert _verify_jwt_signature(rs_token) is None
        hs_token = pyjwt.encode(payload, "strong-secret-32bytes-for-hs256-test", algorithm="HS256")
        mk, mc = MagicMock(), MagicMock()
        mk.key = pub_pem
        mc.get_signing_key_from_jwt.return_value = mk
        with patch("jwt.PyJWKClient", return_value=mc):
            assert _verify_jwt_rs256(hs_token) is None

    def test_hs256_allowlist_retained(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import jwt as pyjwt

        secret = "s3-guard-secret-32bytes-strong-123456"
        monkeypatch.setenv("SUPABASE_JWT_SECRET", secret)
        from bot.config import validate_supabase_key

        validate_supabase_key(pyjwt.encode({"role": "service_role"}, secret, algorithm="HS256"))

    def test_validate_supabase_key_rs256_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import jwt as pyjwt

        priv_pem, pub_pem = _rsa_pair()
        monkeypatch.setenv("SUPABASE_JWKS_URL", "https://proj.supabase.co/auth/v1/.well-known/jwks.json")
        monkeypatch.setenv("SUPABASE_JWT_ISSUER", "https://proj.supabase.co/auth/v1")
        monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
        monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
        token = pyjwt.encode(
            {
                "role": "service_role",
                "iss": "https://proj.supabase.co/auth/v1",
                "aud": "authenticated",
                "exp": int(time.time()) + 600,
            },
            priv_pem,
            algorithm="RS256",
            headers={"kid": "k1"},
        )
        from bot.config import validate_supabase_key

        mk, mc = MagicMock(), MagicMock()
        mk.key = pub_pem
        mc.get_signing_key_from_jwt.return_value = mk
        with patch("jwt.PyJWKClient", return_value=mc):
            validate_supabase_key(token)

    def test_direct_pyjwt_crypto_dependency(self) -> None:
        from pathlib import Path

        assert (
            "PyJWT" in Path("pyproject.toml").read_text(encoding="utf-8")
            and "crypto" in Path("pyproject.toml").read_text(encoding="utf-8").lower()
        )
