from datetime import datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import (
    create_reservation_cancel_token,
    create_signed_guest_token,
    generate_opaque_token,
    hash_token,
)
from app.models import (
    DiscountType,
    ItemCustomization,
    MenuItem,
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    PaymentStatus,
    PromoCode,
    Reservation,
    ReservationStatus,
    RestaurantSettings,
    RestaurantTable,
    TableSession,
    TableSessionStatus,
    User,
)
from app.schemas import CreateOrderRequest, CreateReservationRequest
from app.services.email import send_order_confirmation, send_reservation_confirmation


async def get_global_customizations(db: AsyncSession) -> list[ItemCustomization]:
    result = await db.execute(select(ItemCustomization).where(ItemCustomization.is_global.is_(True)))
    return list(result.scalars().all())


async def resolve_table_session(db: AsyncSession, token: str | None) -> TableSession | None:
    if not token:
        return None

    result = await validate_or_open_session_from_qr(db, token)
    if result:
        _, session = result
        return session
    return None


async def open_table_session(db: AsyncSession, table_id: UUID) -> tuple[str, TableSession]:
    token = generate_opaque_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.table_session_hours)
    session = TableSession(
        table_id=table_id,
        token_hash=hash_token(token),
        expires_at=expires,
        status=TableSessionStatus.active,
    )
    db.add(session)
    await db.flush()
    return token, session


async def validate_or_open_session_from_qr(db: AsyncSession, qr_token: str) -> tuple[str, TableSession] | None:
    """QR encodes a stable opaque table token stored on the table row."""
    table_result = await db.execute(select(RestaurantTable).where(RestaurantTable.qr_code_url == qr_token))
    table = table_result.scalar_one_or_none()
    if not table:
        return None

    active = await db.execute(
        select(TableSession).where(
            TableSession.table_id == table.id,
            TableSession.status == TableSessionStatus.active,
            TableSession.expires_at > datetime.now(timezone.utc),
        )
    )
    existing = active.scalar_one_or_none()
    if existing:
        # Return the qr token for URL; session already active
        return qr_token, existing

    session_token, session = await open_table_session(db, table.id)
    return qr_token, session


async def calculate_order_totals(
    db: AsyncSession,
    request: CreateOrderRequest,
    user: User | None,
    table_session: TableSession | None,
) -> tuple[list[dict], float, float, float, float, PromoCode | None, int]:
    global_customizations = await get_global_customizations(db)
    global_map = {c.id: c for c in global_customizations}

    line_items: list[dict] = []
    subtotal = 0.0

    for item_req in request.items:
        result = await db.execute(
            select(MenuItem)
            .options(selectinload(MenuItem.customizations))
            .where(MenuItem.id == item_req.menu_item_id, MenuItem.is_available.is_(True))
        )
        menu_item = result.scalar_one_or_none()
        if not menu_item:
            raise ValueError(f"Menu item {item_req.menu_item_id} not available")

        item_custom_map = {c.id: c for c in menu_item.customizations}
        extras = 0.0
        selected: dict = {"customizations": []}

        for cid in item_req.customization_ids:
            custom = item_custom_map.get(cid) or global_map.get(cid)
            if custom:
                extras += custom.extra_price
                selected["customizations"].append({"id": str(cid), "name": custom.name, "price": custom.extra_price})

        unit_price = menu_item.price + extras
        line_price = unit_price * item_req.quantity
        subtotal += line_price

        line_items.append(
            {
                "menu_item_id": menu_item.id,
                "item_name": menu_item.name,
                "quantity": item_req.quantity,
                "selected_customizations": selected,
                "line_price": line_price,
            }
        )

    promo: PromoCode | None = None
    discount = 0.0
    if request.promo_code:
        promo_result = await db.execute(
            select(PromoCode).where(
                PromoCode.code == request.promo_code.upper(),
                PromoCode.is_active.is_(True),
            )
        )
        promo = promo_result.scalar_one_or_none()
        if promo and (not promo.expires_at or promo.expires_at > datetime.now(timezone.utc)):
            if promo.usage_limit is None or promo.used_count < promo.usage_limit:
                if promo.discount_type == DiscountType.percent:
                    discount = subtotal * (promo.discount_value / 100)
                else:
                    discount = min(promo.discount_value, subtotal)

    loyalty_discount = 0.0
    points_redeem = request.loyalty_points_redeem
    if user and points_redeem > 0:
        points_redeem = min(points_redeem, user.loyalty_points)
        loyalty_discount = float(points_redeem)

    discount += loyalty_discount
    taxable = max(subtotal - discount, 0)
    tax = taxable * settings.gst_rate
    total = taxable + tax + request.tip

    points_earned = int(taxable * settings.loyalty_points_per_rupee) if user else 0

    return line_items, subtotal, tax, discount, total, promo, points_earned


async def create_order(
    db: AsyncSession,
    request: CreateOrderRequest,
    user: User | None,
    table_session: TableSession | None,
) -> Order:
    if request.order_type == "dine_in" and not table_session:
        raise ValueError("Valid table session required for dine-in orders")

    line_items, subtotal, tax, discount, total, promo, points_earned = await calculate_order_totals(
        db, request, user, table_session
    )

    payment_status = PaymentStatus.pending
    if request.payment_method == "pay_at_counter":
        payment_status = PaymentStatus.pay_at_counter

    order = Order(
        user_id=user.id if user else None,
        order_type=OrderType.pickup if request.order_type == "pickup" else OrderType.dine_in,
        table_id=table_session.table_id if table_session else None,
        table_session_id=table_session.id if table_session else None,
        status=OrderStatus.received,
        subtotal=subtotal,
        tax=tax,
        discount=discount,
        tip=request.tip,
        total=total,
        promo_code_id=promo.id if promo else None,
        payment_status=payment_status,
        pickup_time=request.pickup_time,
        guest_email=str(request.guest_email) if request.guest_email else None,
        guest_name=request.guest_name,
        guest_phone=request.guest_phone,
        loyalty_points_earned=points_earned,
    )
    db.add(order)
    await db.flush()

    for li in line_items:
        db.add(OrderItem(order_id=order.id, **li))

    if promo:
        promo.used_count += 1

    if user and request.loyalty_points_redeem > 0:
        redeem = min(request.loyalty_points_redeem, user.loyalty_points)
        user.loyalty_points -= redeem

    if user and request.payment_method == "pay_at_counter":
        user.loyalty_points += points_earned

    await db.flush()
    return order


async def get_availability(db: AsyncSession, target_date) -> list[dict]:
    settings_result = await db.execute(select(RestaurantSettings).limit(1))
    restaurant = settings_result.scalar_one_or_none()
    max_per_slot = restaurant.max_reservations_per_slot if restaurant else 5

    open_time = datetime.strptime("11:00", "%H:%M").time()
    close_time = datetime.strptime("23:00", "%H:%M").time()

    # Fetch all reservations for the target date in a SINGLE query
    res_result = await db.execute(
        select(Reservation).where(
            Reservation.date == target_date,
            Reservation.status.in_([ReservationStatus.pending, ReservationStatus.confirmed]),
        )
    )
    all_reservations = res_result.scalars().all()
    
    # Group by slot time
    slot_counts = {}
    for r in all_reservations:
        slot_str = r.time.strftime("%H:%M")
        slot_counts[slot_str] = slot_counts.get(slot_str, 0) + 1

    slots = []
    current = datetime.combine(target_date, open_time)
    end = datetime.combine(target_date, close_time)

    while current < end:
        slot_time = current.time()
        slot_str = slot_time.strftime("%H:%M")
        
        count = slot_counts.get(slot_str, 0)
        remaining = max(max_per_slot - count, 0)
        
        slots.append(
            {
                "time": slot_str,
                "available": remaining > 0,
                "remaining": remaining,
            }
        )
        current += timedelta(minutes=30)

    return slots


async def create_reservation(db: AsyncSession, request: CreateReservationRequest, user: User | None) -> Reservation:
    slots = await get_availability(db, request.date)
    slot = next((s for s in slots if s["time"] == request.time.strftime("%H:%M")), None)
    if not slot or not slot["available"]:
        raise ValueError("Selected time slot is not available")

    reservation = Reservation(
        user_id=user.id if user else None,
        name=request.name,
        phone=request.phone,
        email=request.email,
        party_size=request.party_size,
        date=request.date,
        time=request.time,
        status=ReservationStatus.confirmed,
        special_requests=request.special_requests,
    )
    db.add(reservation)
    try:
        await db.flush()
    except IntegrityError:
        raise ValueError("You already have a reservation for this time under this email address.")
    return reservation
