"""
KEM Data Plug — FastAPI Backend

Paystack-powered data bundle sales for MTN, Vodafone, AirtelTigo.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import Base, engine, get_db
from backend.models import (
    Transaction,
    DeliveryLog,
    TransactionStatus,
    PaymentChannel,
    DeliveryStatus,
    NETWORKS,
    PRICING_BY_NETWORK,
    generate_ref,
)
from backend.paystack import initialize_transaction, verify_transaction, verify_webhook_signature
from backend.telecom import deliver_data
from backend.admin import router as admin_router

# ─── Logging ──────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── App ──────────────────────────────────────────────────────
app = FastAPI(
    title="KEM Data Plug API",
    version="1.0.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)

# Create tables on startup
Base.metadata.create_all(bind=engine)


# ─── Schemas ──────────────────────────────────────────────────

class InitiatePaymentRequest(BaseModel):
    network: str = Field(..., description="mtn, vodafone, or airteltigo")
    data_plan: str = Field(..., description="e.g. 5GB, 10GB, 50GB")
    recipient_phone: str = Field(..., min_length=10, max_length=15)
    payer_phone: Optional[str] = Field(None, min_length=10, max_length=15)
    email: Optional[str] = Field(None)


class InitiatePaymentResponse(BaseModel):
    success: bool
    authorization_url: Optional[str] = None
    access_code: Optional[str] = None
    reference: Optional[str] = None
    amount: Optional[float] = None
    message: Optional[str] = None


class PaymentStatusResponse(BaseModel):
    success: bool
    reference: str
    status: str
    delivery_status: Optional[str] = None
    amount: Optional[float] = None
    network: Optional[str] = None
    data_plan: Optional[str] = None
    recipient_phone: Optional[str] = None


# ─── Endpoints ────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "KEM Data Plug API"}


@app.post("/api/initiate-payment", response_model=InitiatePaymentResponse)
async def handle_initiate_payment(req: InitiatePaymentRequest, db: Session = Depends(get_db)):
    """Step 1: Create transaction + initialize Paystack checkout."""

    # Validate network
    network = req.network.lower()
    if network not in NETWORKS:
        raise HTTPException(400, f"Invalid network. Choose: {', '.join(NETWORKS.keys())}")

    # Validate data plan and get price
    net_pricing = PRICING_BY_NETWORK.get(network, [])
    plan = next((p for p in net_pricing if p["data"].upper() == req.data_plan.upper()), None)
    if not plan:
        raise HTTPException(400, f"Invalid data plan: {req.data_plan}")

    amount = plan["price"]

    # Validate phone
    phone = req.recipient_phone.strip()
    if not phone.startswith("0") or len(phone) < 10:
        raise HTTPException(400, "Recipient phone must be a valid Ghana number (e.g. 0540363205)")

    # Generate reference
    reference = generate_ref()
    email = req.email or f"{phone}@kemdataplug.com"

    # Create pending transaction
    tx = Transaction(
        reference=reference,
        network=network,
        data_plan=plan["data"],
        amount=amount,
        recipient_phone=phone,
        payer_phone=req.payer_phone or phone,
        status=TransactionStatus.PENDING,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)

    logger.info(f"Transaction {reference} created: {network} {plan['data']} = GH₵{amount}")

    # Initialize Paystack
    callback_url = f"{settings.app_url.rstrip('/')}/payment-callback?reference={reference}"
    paystack_resp = await initialize_transaction(
        email=email,
        amount=amount,
        reference=reference,
        callback_url=callback_url,
        metadata={
            "reference": reference,
            "network": network,
            "data_plan": plan["data"],
            "recipient_phone": phone,
        },
    )

    if not paystack_resp.get("status"):
        error_msg = paystack_resp.get("message", "Paystack initialization failed")
        # Mark transaction as failed
        tx.status = TransactionStatus.FAILED
        db.commit()
        logger.error(f"Paystack init failed for {reference}: {error_msg}")
        raise HTTPException(502, f"Payment gateway error: {error_msg}")

    auth_url = paystack_resp["data"]["authorization_url"]
    paystack_ref = paystack_resp["data"]["reference"]
    tx.paystack_ref = paystack_ref
    db.commit()

    return InitiatePaymentResponse(
        success=True,
        authorization_url=auth_url,
        access_code=paystack_resp["data"].get("access_code", ""),
        reference=reference,
        amount=amount,
        message="Redirect user to Paystack checkout",
    )


@app.get("/api/verify-payment")
async def handle_verify_payment(reference: str, db: Session = Depends(get_db)):
    """Step 2: Verify payment status after user returns from Paystack."""
    tx = db.query(Transaction).filter(Transaction.reference == reference).first()
    if not tx:
        raise HTTPException(404, "Transaction not found")

    # If already successful, return cached
    if tx.status == TransactionStatus.SUCCESS:
        return PaymentStatusResponse(
            success=True,
            reference=tx.reference,
            status="successful",
            delivery_status=tx.delivery_status.value if tx.delivery_status else None,
            amount=tx.amount,
            network=tx.network,
            data_plan=tx.data_plan,
            recipient_phone=tx.recipient_phone,
        )

    # Verify with Paystack
    if tx.paystack_ref:
        verify_resp = await verify_transaction(tx.paystack_ref)
        paystack_status = verify_resp.get("data", {}).get("status")

        if paystack_status == "success":
            await _handle_successful_payment(tx, verify_resp["data"], db)
            return PaymentStatusResponse(
                success=True,
                reference=tx.reference,
                status="successful",
                delivery_status=tx.delivery_status.value if tx.delivery_status else None,
                amount=tx.amount,
                network=tx.network,
                data_plan=tx.data_plan,
                recipient_phone=tx.recipient_phone,
            )
        elif paystack_status in ("failed", "abandoned", "reversed"):
            tx.status = TransactionStatus.FAILED
            db.commit()

    return PaymentStatusResponse(
        success=False,
        reference=reference,
        status=tx.status.value,
        message="Payment not yet completed",
    )


@app.post("/api/webhook/paystack")
async def handle_paystack_webhook(request: Request, db: Session = Depends(get_db)):
    """Step 3: Paystack sends webhook on payment success/failure."""
    body = await request.body()
    signature = request.headers.get("x-paystack-signature", "")

    # Verify authenticity
    if not verify_webhook_signature(body, signature):
        logger.warning("Invalid webhook signature")
        raise HTTPException(401, "Invalid signature")

    event = json.loads(body)
    logger.info(f"Paystack webhook: {event.get('event')}")

    # Only handle charge.success
    if event.get("event") != "charge.success":
        return {"status": "ignored", "event": event.get("event")}

    data = event.get("data", {})
    reference = data.get("reference", "")
    metadata = data.get("metadata", {})

    # Find by paystack reference
    tx = db.query(Transaction).filter(
        Transaction.paystack_ref == reference
    ).first()

    if not tx:
        # Try by internal reference from metadata
        internal_ref = metadata.get("reference", "")
        if internal_ref:
            tx = db.query(Transaction).filter(Transaction.reference == internal_ref).first()

    if not tx:
        logger.warning(f"Transaction not found for Paystack ref: {reference}")
        return {"status": "not_found"}

    if tx.status == TransactionStatus.SUCCESS:
        logger.info(f"Transaction {tx.reference} already processed")
        return {"status": "already_processed"}

    await _handle_successful_payment(tx, data, db)
    return {"status": "processed"}


async def _handle_successful_payment(tx: Transaction, paystack_data: dict, db: Session):
    """Handle a successful payment: update DB, deliver data."""
    # Determine payment channel
    channel = paystack_data.get("channel", "")
    if "mobile_money" in channel or "ussd" in channel:
        tx.payment_channel = PaymentChannel.MOBILE_MONEY
    elif "card" in channel or "bank" in channel:
        tx.payment_channel = PaymentChannel.CARD
    else:
        tx.payment_channel = PaymentChannel.UNKNOWN

    tx.status = TransactionStatus.SUCCESS
    tx.paid_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tx)

    logger.info(f"Payment confirmed for {tx.reference}. Delivering data...")

    # Deliver data bundle via telecom API
    delivery_result = await deliver_data(
        network=tx.network,
        data_plan=tx.data_plan,
        recipient_phone=tx.recipient_phone,
        transaction_ref=tx.reference,
    )

    # Update delivery status
    if delivery_result.get("status") == "success":
        tx.delivery_status = DeliveryStatus.DELIVERED
        tx.delivered_at = datetime.now(timezone.utc)
    else:
        tx.delivery_status = DeliveryStatus.FAILED

    tx.delivery_response = json.dumps(delivery_result)
    db.commit()

    # Log delivery
    log = DeliveryLog(
        transaction_id=tx.id,
        reference=tx.reference,
        network=tx.network,
        data_plan=tx.data_plan,
        recipient_phone=tx.recipient_phone,
        status=tx.delivery_status.value,
        response_payload=json.dumps(delivery_result),
    )
    db.add(log)
    db.commit()

    logger.info(f"Delivery {tx.reference}: {tx.delivery_status.value}")


@app.get("/payment-callback")
async def payment_callback(reference: str, db: Session = Depends(get_db)):
    """
    Redirect from Paystack after payment.
    Shows a simple status page that the user can close.
    """
    tx = db.query(Transaction).filter(Transaction.reference == reference).first()
    status = tx.status.value if tx else "unknown"
    delivery = tx.delivery_status.value if tx else "unknown"
    amount = tx.amount if tx else 0
    network = tx.network if tx else ""
    data_plan = tx.data_plan if tx else ""

    success = status == "successful"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Payment {'Successful' if success else 'Status'} — KEM Data Plug</title>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family:'Inter',-apple-system,sans-serif; background:#0E0C0A; color:#EDEAE6; min-height:100vh; display:flex; align-items:center; justify-content:center; }}
    .card {{ background:#1A1612; border-radius:16px; padding:40px; max-width:420px; width:90%; text-align:center; border:1px solid rgba(255,255,255,0.07); }}
    .icon {{ font-size:3rem; margin-bottom:16px; }}
    h1 {{ font-size:1.3rem; font-weight:700; margin-bottom:8px; }}
    p {{ color:#A89A8C; font-size:0.88rem; line-height:1.6; margin-bottom:16px; }}
    .detail {{ background:rgba(255,255,255,0.04); border-radius:10px; padding:14px; margin-bottom:16px; font-size:0.85rem; text-align:left; }}
    .detail-row {{ display:flex; justify-content:space-between; padding:4px 0; }}
    .detail-label {{ color:#A89A8C; }}
    .btn {{ display:inline-block; padding:12px 28px; border-radius:30px; background:linear-gradient(135deg,#F5A623,#E8830A); color:#1A1410; font-weight:600; text-decoration:none; font-size:0.88rem; border:none; cursor:pointer; }}
    .btn:hover {{ transform:scale(1.03); }}
    @media (max-width:480px) {{ .card {{ padding:28px 20px; }} }}
  </style>
</head>
<body>
<div class="card">
  <div class="icon">{'✅' if success else '⏳'}</div>
  <h1>{'Payment Successful!' if success else 'Processing Payment...'}</h1>
  <p>{'We have received your payment and the data is being sent to your number.' if success else 'Your payment is being processed. This may take a moment.'}</p>
  <div class="detail">
    <div class="detail-row"><span class="detail-label">Reference</span><span>{reference}</span></div>
    <div class="detail-row"><span class="detail-label">Network</span><span>{network.upper() if network else '-'}</span></div>
    <div class="detail-row"><span class="detail-label">Data</span><span>{data_plan}</span></div>
    <div class="detail-row"><span class="detail-label">Amount</span><span>GH₵ {amount:.0f}</span></div>
    <div class="detail-row"><span class="detail-label">Status</span><span style="color:{'#34D399' if success else '#F5A623'}">{status.title()}</span></div>
    <div class="detail-row"><span class="detail-label">Delivery</span><span style="color:{'#34D399' if success else '#A89A8C'}">{delivery.title()}</span></div>
  </div>
  <a href="{settings.app_url}" class="btn">Back to Store</a>
</div>
<script>
if ({'true' if not success else 'false'}) {{
  setTimeout(() => window.location.href = '/payment-callback?reference={reference}', 3000);
}}
</script>
</body>
</html>"""
    return HTMLResponse(content=html)
