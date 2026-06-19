import hashlib
import hmac
import json
from typing import Optional
import httpx
from backend.config import settings


# ─── Paystack API ──────────────────────────────────────────────

PAYSTACK_BASE = "https://api.paystack.co"


async def _paystack_post(path: str, data: dict) -> dict:
    """Call Paystack POST endpoint."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{PAYSTACK_BASE}{path}",
            json=data,
            headers={
                "Authorization": f"Bearer {settings.paystack_secret_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        return r.json()


async def _paystack_get(path: str) -> dict:
    """Call Paystack GET endpoint."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{PAYSTACK_BASE}{path}",
            headers={
                "Authorization": f"Bearer {settings.paystack_secret_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        return r.json()


async def initialize_transaction(
    email: str,
    amount: float,  # in GHS
    reference: str,
    callback_url: str,
    metadata: Optional[dict] = None,
) -> dict:
    """
    Initialize a Paystack transaction.
    Returns {'status': True, 'data': {'authorization_url': '...', 'reference': '...'}}
    """
    payload = {
        "email": email,
        "amount": int(amount * 100),  # Paystack uses pesewas (GHS * 100)
        "reference": reference,
        "callback_url": callback_url,
        "currency": "GHS",
        "channels": ["mobile_money", "card"],  # Mobile Money + Card
    }
    if metadata:
        payload["metadata"] = metadata
    return await _paystack_post("/transaction/initialize", payload)


async def verify_transaction(reference: str) -> dict:
    """Verify a Paystack transaction by reference."""
    return await _paystack_get(f"/transaction/verify/{reference}")


def verify_webhook_signature(payload_body: bytes, signature_header: str) -> bool:
    """
    Verify that a Paystack webhook is authentic.
    Paystack signs webhooks with HMAC-SHA512 using the secret key.
    """
    if not signature_header:
        return False
    expected = hmac.new(
        settings.paystack_secret_key.encode("utf-8"),
        payload_body,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
