import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Enum as SAEnum
from backend.database import Base
import enum


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "successful"
    FAILED = "failed"


class PaymentChannel(str, enum.Enum):
    MOBILE_MONEY = "mobile_money"
    CARD = "card"
    UNKNOWN = "unknown"


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


NETWORKS = {
    "mtn": "MTN Ghana",
    "vodafone": "Vodafone Ghana",
    "airteltigo": "AirtelTigo",
}

PRICING = [
    {"data": "1GB", "price": 5},
    {"data": "2GB", "price": 10},
    {"data": "3GB", "price": 13},
    {"data": "4GB", "price": 19},
    {"data": "5GB", "price": 23},
    {"data": "6GB", "price": 28},
    {"data": "7GB", "price": 30},
    {"data": "8GB", "price": 37},
    {"data": "10GB", "price": 47},
    {"data": "15GB", "price": 68},
    {"data": "20GB", "price": 88},
    {"data": "25GB", "price": 108},
    {"data": "30GB", "price": 128},
    {"data": "40GB", "price": 170},
    {"data": "50GB", "price": 220},
    {"data": "100GB", "price": 420},
    {"data": "200GB", "price": 790},
]


def generate_ref() -> str:
    return f"KDP-{uuid.uuid4().hex[:12].upper()}"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String(64), unique=True, index=True, nullable=False, default=generate_ref)
    paystack_ref = Column(String(128), nullable=True)

    network = Column(String(32), nullable=False)
    data_plan = Column(String(16), nullable=False)
    amount = Column(Float, nullable=False)
    recipient_phone = Column(String(20), nullable=False)
    payer_phone = Column(String(20), nullable=True)

    status = Column(SAEnum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False)
    payment_channel = Column(SAEnum(PaymentChannel), default=PaymentChannel.UNKNOWN, nullable=False)

    delivery_status = Column(SAEnum(DeliveryStatus), default=DeliveryStatus.PENDING, nullable=False)
    delivery_response = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    paid_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)


class DeliveryLog(Base):
    __tablename__ = "delivery_logs"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, nullable=False)
    reference = Column(String(64), nullable=False)
    network = Column(String(32))
    data_plan = Column(String(16))
    recipient_phone = Column(String(20))
    status = Column(String(32), default="pending")
    request_payload = Column(Text, nullable=True)
    response_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
