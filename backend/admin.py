"""
A simple admin dashboard rendered as HTML from FastAPI.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Transaction, TransactionStatus, DeliveryStatus

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    # Stats
    total_tx = db.query(func.count(Transaction.id)).scalar() or 0
    total_revenue = db.query(func.sum(Transaction.amount)).filter(
        Transaction.status == TransactionStatus.SUCCESS
    ).scalar() or 0.0
    successful = db.query(func.count(Transaction.id)).filter(
        Transaction.status == TransactionStatus.SUCCESS
    ).scalar() or 0
    pending = db.query(func.count(Transaction.id)).filter(
        Transaction.status == TransactionStatus.PENDING
    ).scalar() or 0
    failed = db.query(func.count(Transaction.id)).filter(
        Transaction.status == TransactionStatus.FAILED
    ).scalar() or 0

    # Recent transactions
    recent = (
        db.query(Transaction)
        .order_by(Transaction.created_at.desc())
        .limit(50)
        .all()
    )

    # Delivery stats
    delivered = db.query(func.count(Transaction.id)).filter(
        Transaction.delivery_status == DeliveryStatus.DELIVERED
    ).scalar() or 0
    delivery_pending = db.query(func.count(Transaction.id)).filter(
        Transaction.delivery_status == DeliveryStatus.PENDING
    ).scalar() or 0
    delivery_failed = db.query(func.count(Transaction.id)).filter(
        Transaction.delivery_status == DeliveryStatus.FAILED
    ).scalar() or 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>KEM Data Plug — Admin</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family:'Inter',sans-serif; background:#0E0C0A; color:#EDEAE6; min-height:100vh; }}
    .nav {{ padding:16px 24px; border-bottom:1px solid rgba(255,255,255,0.07); display:flex; align-items:center; justify-content:space-between; }}
    .nav h1 {{ font-size:1.1rem; font-weight:700; }}
    .nav a {{ color:#F5A623; text-decoration:none; font-size:0.85rem; }}
    .container {{ max-width:1100px; margin:0 auto; padding:24px; }}
    .stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:28px; }}
    .stat-card {{ padding:20px; border-radius:12px; background:#1A1612; border:1px solid rgba(255,255,255,0.07); }}
    .stat-card .num {{ font-size:1.5rem; font-weight:700; font-family:'Inter',sans-serif; }}
    .stat-card .label {{ font-size:0.78rem; color:#A89A8C; margin-top:2px; }}
    .stat-card.gold {{ border-color:rgba(245,166,35,0.18); background:rgba(245,166,35,0.05); }}
    .stat-card.green {{ border-color:rgba(52,211,153,0.15); background:rgba(52,211,153,0.05); }}
    .stat-card.red {{ border-color:rgba(239,68,68,0.15); background:rgba(239,68,68,0.05); }}
    h2 {{ font-size:1rem; font-weight:600; margin-bottom:14px; }}
    table {{ width:100%; border-collapse:collapse; font-size:0.82rem; }}
    th, td {{ padding:10px 12px; text-align:left; border-bottom:1px solid rgba(255,255,255,0.06); }}
    th {{ color:#A89A8C; font-weight:500; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.5px; }}
    .badge {{ display:inline-block; padding:2px 8px; border-radius:100px; font-size:0.7rem; font-weight:600; }}
    .badge-success {{ background:rgba(52,211,153,0.1); color:#34D399; }}
    .badge-pending {{ background:rgba(245,166,35,0.1); color:#F5A623; }}
    .badge-failed {{ background:rgba(239,68,68,0.1); color:#EF4444; }}
    .mono {{ font-family:monospace; font-size:0.75rem; color:#A89A8C; }}
    .section {{ margin-bottom:32px; }}
    @media (max-width:768px) {{ table {{ font-size:0.7rem; }} th,td {{ padding:6px 8px; }} }}
  </style>
</head>
<body>
<div class="nav">
  <h1>⚡ KEM Data Plug — Admin</h1>
  <a href="/docs">API Docs</a>
</div>
<div class="container">
  <div class="stats">
    <div class="stat-card gold">
      <div class="num">GH₵ {total_revenue:,.2f}</div>
      <div class="label">Total Revenue</div>
    </div>
    <div class="stat-card green">
      <div class="num">{successful}</div>
      <div class="label">Successful</div>
    </div>
    <div class="stat-card">
      <div class="num">{pending}</div>
      <div class="label">Pending</div>
    </div>
    <div class="stat-card red">
      <div class="num">{failed}</div>
      <div class="label">Failed</div>
    </div>
    <div class="stat-card">
      <div class="num">{total_tx}</div>
      <div class="label">Total Transactions</div>
    </div>
    <div class="stat-card green">
      <div class="num">{delivered}</div>
      <div class="label">Data Delivered</div>
    </div>
  </div>

  <div class="section">
    <h2>📋 Recent Transactions</h2>
    <table>
      <thead>
        <tr>
          <th>Reference</th>
          <th>Network</th>
          <th>Plan</th>
          <th>Amount</th>
          <th>Recipient</th>
          <th>Payment</th>
          <th>Delivery</th>
          <th>Date</th>
        </tr>
      </thead>
      <tbody>
"""
    for tx in recent:
        payment_badge = {
            TransactionStatus.PENDING: '<span class="badge badge-pending">Pending</span>',
            TransactionStatus.SUCCESS: '<span class="badge badge-success">Paid</span>',
            TransactionStatus.FAILED: '<span class="badge badge-failed">Failed</span>',
        }.get(tx.status, '<span class="badge badge-pending">?</span>')

        delivery_badge = {
            DeliveryStatus.PENDING: '<span class="badge badge-pending">Pending</span>',
            DeliveryStatus.DELIVERED: '<span class="badge badge-success">Done</span>',
            DeliveryStatus.FAILED: '<span class="badge badge-failed">Failed</span>',
        }.get(tx.delivery_status, '<span class="badge badge-pending">?</span>')

        date_str = tx.created_at.strftime("%d %b %H:%M") if tx.created_at else "-"
        net = tx.network.upper() if tx.network else "-"

        html += f"""        <tr>
          <td class="mono">{tx.reference}</td>
          <td>{net}</td>
          <td>{tx.data_plan}</td>
          <td>GH₵ {tx.amount:.0f}</td>
          <td>{tx.recipient_phone}</td>
          <td>{payment_badge}</td>
          <td>{delivery_badge}</td>
          <td>{date_str}</td>
        </tr>
"""

    html += """      </tbody>
    </table>
  </div>
</div>
</body>
</html>"""
    return HTMLResponse(content=html)
