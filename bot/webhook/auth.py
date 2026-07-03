"""HMAC-SHA256 signature helpers for webhook verification.

The dashboard signs the raw request body with ``WEBHOOK_SECRET`` and sends
the hexdigest in the ``X-Webhook-Signature`` header. The bot verifies the
signature in constant time via :func:`hmac.compare_digest`.

Per the cache-sync-webhook spec, verification uses HMAC-SHA256 — simple
shared-secret auth/integrity between Vercel and the bot.
"""

from __future__ import annotations

import hashlib
import hmac

# Header carrying the HMAC-SHA256 hexdigest of the raw body.
SIGNATURE_HEADER = "X-Webhook-Signature"


def compute_signature(body: bytes, secret: str) -> str:
    """Return the HMAC-SHA256 hexdigest of *body* under *secret*.

    Args:
        body: The raw request body bytes.
        secret: The shared webhook secret.

    Returns:
        The lowercase hexadecimal HMAC-SHA256 digest.
    """
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, signature: str | None, secret: str) -> bool:
    """Verify *signature* against the computed HMAC of *body* in constant time.

    Args:
        body: The raw request body bytes.
        signature: The hexdigest from the ``X-Webhook-Signature`` header,
            or ``None``/empty when the header is absent.
        secret: The shared webhook secret.

    Returns:
        ``True`` if the signature matches, ``False`` otherwise. Returns
        ``False`` when the secret is empty (defensive — the server should
        not start without a secret) or when the signature is missing.
    """
    if not secret or not signature:
        return False

    expected = compute_signature(body, secret)
    return hmac.compare_digest(expected, signature)
