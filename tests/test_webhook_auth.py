"""Unit tests for bot.webhook.auth — HMAC-SHA256 signature helpers.

Covers the cache-sync-webhook spec — HMAC signature verification:
    - Valid signature accepted (constant-time compare)
    - Missing signature rejected
    - Tampered/invalid signature rejected
    - Empty secret behaviour
"""

from __future__ import annotations

import hashlib
import hmac

from bot.webhook.auth import compute_signature, verify_signature

_SECRET = "test-webhook-secret"
_BODY = b'{"guild_id": 12345, "entity": "guild_config"}'


def _expected_hex(body: bytes, secret: str) -> str:
    """Reference HMAC-SHA256 hexdigest for triangulation."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# compute_signature
# ---------------------------------------------------------------------------


class TestComputeSignature:
    def test_matches_reference_hmac_sha256(self) -> None:
        sig = compute_signature(_BODY, _SECRET)

        assert sig == _expected_hex(_BODY, _SECRET)

    def test_different_body_produces_different_signature(self) -> None:
        """Triangulation: a different body MUST yield a different signature."""
        other_body = b'{"guild_id": 99999}'

        assert compute_signature(other_body, _SECRET) != compute_signature(_BODY, _SECRET)

    def test_different_secret_produces_different_signature(self) -> None:
        """Triangulation: a different secret MUST yield a different signature."""
        assert compute_signature(_BODY, "other-secret") != compute_signature(_BODY, _SECRET)


# ---------------------------------------------------------------------------
# verify_signature
# ---------------------------------------------------------------------------


class TestVerifySignature:
    def test_valid_signature_accepted(self) -> None:
        """Spec: valid signature -> accepted (returns True)."""
        sig = _expected_hex(_BODY, _SECRET)

        assert verify_signature(_BODY, sig, _SECRET) is True

    def test_missing_signature_rejected(self) -> None:
        """Spec: missing signature header -> rejected (returns False)."""
        assert verify_signature(_BODY, "", _SECRET) is False

        assert verify_signature(_BODY, None, _SECRET) is False  # type: ignore[arg-type]

    def test_tampered_signature_rejected(self) -> None:
        """Spec: wrong/tampered signature -> rejected."""
        valid = _expected_hex(_BODY, _SECRET)
        tampered = valid[:-2] + "00"

        assert verify_signature(_BODY, tampered, _SECRET) is False

    def test_wrong_secret_signature_rejected(self) -> None:
        """A signature computed with a different secret is rejected."""
        wrong_sig = _expected_hex(_BODY, "wrong-secret")

        assert verify_signature(_BODY, wrong_sig, _SECRET) is False

    def test_empty_secret_rejects_everything(self) -> None:
        """With no secret configured, no signature validates (defensive)."""
        sig = _expected_hex(_BODY, "")

        assert verify_signature(_BODY, sig, "") is False

    def test_returns_bool_not_int(self) -> None:
        """verify_signature MUST return a real bool (not truthy int)."""
        sig = _expected_hex(_BODY, _SECRET)

        result = verify_signature(_BODY, sig, _SECRET)
        assert result is True
        assert isinstance(result, bool)
