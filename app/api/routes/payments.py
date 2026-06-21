from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Order, PaymentStatus
from app.schemas import CreateOrderRequest, PaymentIntentResponse
from app.services.orders import create_order, resolve_table_session
from app.services.payment import confirm_mock_payment, create_payment_intent, handle_stripe_webhook

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/create-intent", response_model=PaymentIntentResponse)
async def create_intent(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    amount_paise = int(order.total * 100)
    intent = await create_payment_intent(amount_paise, str(order_id))
    return PaymentIntentResponse(**intent)


@router.post("/confirm-mock/{order_id}")
async def confirm_mock(order_id: UUID, payment_intent_id: str, db: AsyncSession = Depends(get_db)):
    if not await confirm_mock_payment(payment_intent_id):
        raise HTTPException(status_code=400, detail="Invalid payment intent")

    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.payment_status = PaymentStatus.paid
    order.stripe_payment_id = payment_intent_id
    return {"ok": True, "payment_status": "paid"}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    event = await handle_stripe_webhook(payload, sig)
    if not event:
        return {"received": True}

    if event["type"] == "payment_intent.succeeded":
        order_id = event["data"]["object"]["metadata"].get("order_id")
        if order_id:
            result = await db.execute(select(Order).where(Order.id == UUID(order_id)))
            order = result.scalar_one_or_none()
            if order:
                order.payment_status = PaymentStatus.paid

    return {"received": True}
