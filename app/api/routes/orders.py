from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_current_user_optional, require_staff
from app.core.security import create_reservation_cancel_token, create_signed_guest_token, verify_guest_order_token
from app.db.session import get_db, async_session_maker
from app.models import Order, OrderStatus, User
from app.schemas import (
    AvailabilityResponse,
    CreateOrderRequest,
    CreateReservationRequest,
    OrderResponse,
    ReservationResponse,
    ValidatePromoRequest,
    ValidatePromoResponse,
)
from app.services.email import send_order_confirmation, send_reservation_confirmation
from app.services.orders import (
    create_order,
    create_reservation,
    get_availability,
    resolve_table_session,
    validate_or_open_session_from_qr,
)
from app.models import DiscountType, PromoCode, Reservation, ReservationStatus

router = APIRouter(tags=["orders & reservations"])

order_connections: dict[str, list[WebSocket]] = {}


def order_to_response(order: Order, guest_token: str | None = None) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        order_type=order.order_type.value,
        status=order.status.value,
        subtotal=order.subtotal,
        tax=order.tax,
        discount=order.discount,
        tip=order.tip,
        total=order.total,
        payment_status=order.payment_status.value,
        pickup_time=order.pickup_time,
        loyalty_points_earned=order.loyalty_points_earned,
        created_at=order.created_at,
        items=order.items,
        guest_token=guest_token,
    )


@router.get("/table/validate")
async def validate_table_token(t: str = Query(...), db: AsyncSession = Depends(get_db)):
    session = await validate_or_open_session_from_qr(db, t)
    if not session:
        raise HTTPException(status_code=400, detail="Invalid or expired table token")
    _, table_session = session
    return {"valid": True, "expires_at": table_session.expires_at.isoformat()}


@router.post("/orders", response_model=OrderResponse)
async def place_order(
    request: CreateOrderRequest,
    table_token: str | None = Query(None, alias="t"),
    user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    table_session = await resolve_table_session(db, table_token)
    if request.order_type == "dine_in" and not table_session:
        result = await validate_or_open_session_from_qr(db, table_token or "")
        if result:
            _, table_session = result

    try:
        order = await create_order(db, request, user, table_session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    guest_token = None
    email = request.guest_email or (user.email if user else None)
    if not user:
        guest_token = create_signed_guest_token(str(order.id))

    if email:
        await send_order_confirmation(str(email), str(order.id), order.total, guest_token)

    await db.refresh(order, ["items"])
    return order_to_response(order, guest_token)


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    token: str | None = None,
    user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    authorized = False
    if user and order.user_id == user.id:
        authorized = True
    elif token and verify_guest_order_token(token, str(order_id)):
        authorized = True
    elif user and user.role.value in ("staff", "owner"):
        authorized = True

    if not authorized:
        raise HTTPException(status_code=403, detail="Not authorized to view this order")

    return order_to_response(order)


@router.get("/orders", response_model=list[OrderResponse])
async def list_my_orders(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(50)
    )
    orders = result.scalars().all()
    return [order_to_response(o) for o in orders]


@router.post("/promo/validate", response_model=ValidatePromoResponse)
async def validate_promo(data: ValidatePromoRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PromoCode).where(PromoCode.code == data.code.upper(), PromoCode.is_active.is_(True))
    )
    promo = result.scalar_one_or_none()
    if not promo:
        return ValidatePromoResponse(valid=False, message="Invalid promo code")

    from datetime import datetime, timezone

    if promo.expires_at and promo.expires_at < datetime.now(timezone.utc):
        return ValidatePromoResponse(valid=False, message="Promo code expired")
    if promo.usage_limit is not None and promo.used_count >= promo.usage_limit:
        return ValidatePromoResponse(valid=False, message="Promo code usage limit reached")

    if promo.discount_type == DiscountType.percent:
        discount = data.subtotal * (promo.discount_value / 100)
    else:
        discount = min(promo.discount_value, data.subtotal)

    return ValidatePromoResponse(valid=True, discount=discount, message="Promo applied")


from app.core.redis import get_cache, set_cache
import json
from fastapi.responses import JSONResponse

@router.get("/reservations/availability")
async def reservation_availability(
    date: date = Query(...),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"availability_{date.isoformat()}"
    cached = await get_cache(cache_key)
    if cached:
        return JSONResponse(content=json.loads(cached))

    slots = await get_availability(db, date)
    response_obj = AvailabilityResponse(date=date, slots=slots)
    
    # Cache for 60 seconds (reservations are dynamic but 1min is a safe buffer for UX speed)
    await set_cache(cache_key, response_obj.model_dump_json(), expire_seconds=60)
    
    return response_obj


@router.post("/reservations", response_model=ReservationResponse)
async def book_reservation(
    request: CreateReservationRequest,
    user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    try:
        reservation = await create_reservation(db, request, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    cancel_token = create_reservation_cancel_token(str(reservation.id))
    await send_reservation_confirmation(
        reservation.email,
        reservation.name,
        reservation.date.isoformat(),
        reservation.time.strftime("%H:%M"),
        cancel_token,
    )
    
    # Invalidate cache for this specific date
    from app.core.redis import delete_cache
    await delete_cache(f"availability_{request.date.isoformat()}")
    
    return ReservationResponse(
        id=reservation.id,
        name=reservation.name,
        phone=reservation.phone,
        email=reservation.email,
        party_size=reservation.party_size,
        date=reservation.date,
        time=reservation.time,
        status=reservation.status.value,
        special_requests=reservation.special_requests,
        cancel_token=cancel_token,
    )


@router.post("/reservations/cancel")
async def cancel_reservation(token: str = Query(...), db: AsyncSession = Depends(get_db)):
    from app.core.security import verify_reservation_cancel_token

    payload_valid = False
    reservation_id = None

    from jose import jwt
    from app.core.config import settings

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        reservation_id = payload.get("reservation_id")
        payload_valid = verify_reservation_cancel_token(token, reservation_id)
    except Exception:
        pass

    if not payload_valid or not reservation_id:
        raise HTTPException(status_code=400, detail="Invalid cancel token")

    result = await db.execute(select(Reservation).where(Reservation.id == UUID(reservation_id)))
    reservation = result.scalar_one_or_none()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    reservation.status = ReservationStatus.cancelled
    await db.commit()
    
    from app.core.redis import delete_cache
    await delete_cache(f"availability_{reservation.date.isoformat()}")
    
    return {"ok": True, "message": "Reservation cancelled"}


@router.websocket("/ws/orders/{order_id}")
async def order_status_ws(websocket: WebSocket, order_id: str, token: str | None = None):
    await websocket.accept()
    order_connections.setdefault(order_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        order_connections[order_id].remove(websocket)


async def broadcast_order_status(order_id: str, status: str):
    for ws in order_connections.get(order_id, []):
        try:
            await ws.send_json({"order_id": order_id, "status": status})
        except Exception:
            pass
