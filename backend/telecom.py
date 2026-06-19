"""
Telecom / data vendor API interface.

This module provides a pluggable interface for delivering data bundles
through a telecom vendor API. By default, it uses a mock implementation.
To integrate with a real vendor (e.g. BBS API, VTU API), implement
the `deliver_data` function with the vendor's actual endpoint.

Supported vendors typically in Ghana:
- BBS API (broadband service / data reselling)
- VTU API (virtual top-up)
- Custom vendor API
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
import httpx
from backend.config import settings

logger = logging.getLogger(__name__)

# ─── Mock Delivery (default for testing) ──────────────────────


async def deliver_data_mock(
    network: str,
    data_plan: str,
    recipient_phone: str,
    transaction_ref: str,
) -> dict:
    """
    Mock data delivery — simulates a successful delivery.
    Replace with a real vendor API call in production.
    """
    logger.info(f"[MOCK] Delivering {data_plan} to {network} {recipient_phone} (ref: {transaction_ref})")
    return {
        "status": "success",
        "message": "Data bundle delivered successfully (mock)",
        "reference": transaction_ref,
        "provider_ref": f"MOCK-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
    }


# ─── Real Vendor API (pluggable) ──────────────────────────────

async def deliver_data_vendor(
    network: str,
    data_plan: str,
    recipient_phone: str,
    transaction_ref: str,
) -> dict:
    """
    Deliver data through a real vendor API.
    Adapt this function to the vendor's actual API spec.

    Expected vendor API format (example — adapt as needed):
      POST {vendor_url}/api/topup
      {
        "api_key": "...",
        "network": "mtn|telecel|airteltigo",
        "data_plan": "1GB|2GB|...",
        "phone": "0540363205",
        "reference": "KDP-..."
      }
    """
    if not settings.telecom_api_url or not settings.telecom_api_key:
        logger.warning("Telecom API not configured, falling back to mock")
        return await deliver_data_mock(network, data_plan, recipient_phone, transaction_ref)

    network_map = {
        "mtn": 1,
        "telecel": 2,
        "airteltigo": 4,
    }

    # Parse GB number from plan string (e.g. "10GB" → 10)
    gb_value = int(data_plan.replace("GB", ""))

    payload = {
        "api_key": settings.telecom_api_key,
        "network_id": network_map.get(network, 1),
        "plan": gb_value,
        "phone": recipient_phone,
        "ref": transaction_ref,
    }

    logger.info(f"Calling vendor API: {settings.telecom_api_url} — {payload}")

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                settings.telecom_api_url,
                json=payload,
                timeout=60,
            )
            result = r.json()
            logger.info(f"Vendor response: {result}")
            return {
                "status": "success" if r.is_success else "failed",
                "message": result.get("message", str(result)),
                "reference": transaction_ref,
                "provider_ref": result.get("ref", ""),
                "raw_response": json.dumps(result),
            }
    except Exception as e:
        logger.error(f"Vendor API call failed: {e}")
        return {
            "status": "failed",
            "message": str(e),
            "reference": transaction_ref,
            "provider_ref": "",
            "raw_response": str(e),
        }


# ─── Dispatcher ────────────────────────────────────────────────

async def deliver_data(
    network: str,
    data_plan: str,
    recipient_phone: str,
    transaction_ref: str,
) -> dict:
    """
    Deliver a data bundle. Uses real vendor API if configured,
    otherwise falls back to mock.
    """
    if settings.telecom_api_url:
        return await deliver_data_vendor(network, data_plan, recipient_phone, transaction_ref)
    return await deliver_data_mock(network, data_plan, recipient_phone, transaction_ref)
