from datetime import date, datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_owner, require_staff
from app.api.routes.orders import broadcast_order_status, order_to_response
from app.core.config import settings
from app.core.security import generate_opaque_token, hash_token
from app.db.session import get_db
from app.models import (
    DiscountType,
    MenuCategory,
    MenuItem,
    Order,
    OrderStatus,
    PromoCode,
    Reservation,
    RestaurantSettings,
    RestaurantTable,
    TableSession,
    TableSessionStatus,
    User,
)
from app.schemas import (
    DashboardStats,
    MenuItemCreate,
    MenuItemUpdate,
    OrderResponse,
    OrderStatusUpdate,
    PromoCodeCreate,
    ReservationResponse,
    ReservationStatusUpdate,
    SettingsUpdate,
    TableSessionResponse,
    StaffCreate,
)
from app.services.orders import open_table_session

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard(
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    orders_result = await db.execute(
        select(Order).where(func.date(Order.created_at) == today)
    )
    today_orders = orders_result.scalars().all()
    revenue = sum(o.total for o in today_orders if o.status != OrderStatus.cancelled)

    res_result = await db.execute(
        select(Reservation).where(Reservation.date == today)
    )
    reservations = res_result.scalars().all()

    pending = await db.execute(
        select(Order).where(Order.status.in_([OrderStatus.received, OrderStatus.preparing]))
    )
    pending_orders = len(pending.scalars().all())

    return DashboardStats(
        today_orders=len(today_orders),
        today_revenue=revenue,
        today_reservations=len(reservations),
        pending_orders=pending_orders,
        popular_items=[
            {"name": "DFC Classic Chicken Burger", "count": 12},
            {"name": "Hot Wings (Full)", "count": 8},
        ],
    )


@router.get("/orders", response_model=list[OrderResponse])
async def admin_list_orders(
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).order_by(Order.created_at.desc()).limit(100)
    )
    orders = result.scalars().all()
    return [order_to_response(o) for o in orders]


@router.patch("/orders/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: uuid.UUID,
    data: OrderStatusUpdate,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = OrderStatus(data.status)
    if data.status == "completed" and order.user_id:
        user_result = await db.execute(select(User).where(User.id == order.user_id))
        order_user = user_result.scalar_one_or_none()
        if order_user:
            order_user.loyalty_points += order.loyalty_points_earned

    await broadcast_order_status(str(order_id), data.status)
    return order_to_response(order)


@router.get("/reservations", response_model=list[ReservationResponse])
async def admin_list_reservations(
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Reservation).order_by(Reservation.date.desc(), Reservation.time.desc()))
    reservations = result.scalars().all()
    return [
        ReservationResponse(
            id=r.id,
            name=r.name,
            phone=r.phone,
            email=r.email,
            party_size=r.party_size,
            date=r.date,
            time=r.time,
            status=r.status.value,
            special_requests=r.special_requests,
        )
        for r in reservations
    ]


@router.patch("/reservations/{reservation_id}/status", response_model=ReservationResponse)
async def update_reservation_status(
    reservation_id: uuid.UUID,
    data: ReservationStatusUpdate,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Reservation).where(Reservation.id == reservation_id))
    reservation = result.scalar_one_or_none()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    from app.models import ReservationStatus

    reservation.status = ReservationStatus(data.status)
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
    )


from app.core.redis import delete_cache

@router.post("/menu/item", response_model=dict)
async def create_menu_item(
    data: MenuItemCreate,
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    item = MenuItem(**data.model_dump())
    db.add(item)
    await db.flush()
    await delete_cache("menu_cache*")
    return {"id": str(item.id), "name": item.name}


@router.patch("/menu/item/{item_id}")
async def update_menu_item(
    item_id: uuid.UUID,
    data: MenuItemUpdate,
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MenuItem).where(MenuItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await delete_cache("menu_cache*")
    return {"ok": True}


@router.delete("/menu/item/{item_id}")
async def delete_menu_item(
    item_id: uuid.UUID,
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MenuItem).where(MenuItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.delete(item)
    await db.commit()
    await delete_cache("menu_cache*")
    return {"ok": True}


@router.post("/promo")
async def create_promo(
    data: PromoCodeCreate,
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    promo = PromoCode(
        code=data.code.upper(),
        discount_type=DiscountType(data.discount_type),
        discount_value=data.discount_value,
        expires_at=data.expires_at,
        usage_limit=data.usage_limit,
        per_user_limit=data.per_user_limit,
    )
    db.add(promo)
    await db.flush()
    return {"code": promo.code}


@router.post("/tables/{table_id}/session")
async def manage_table_session(
    table_id: uuid.UUID,
    action: str = "open",
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(RestaurantTable).where(RestaurantTable.id == table_id))
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    if action == "close":
        active = await db.execute(
            select(TableSession).where(
                TableSession.table_id == table_id,
                TableSession.status == TableSessionStatus.active,
            )
        )
        for session in active.scalars().all():
            session.status = TableSessionStatus.closed
            session.closed_reason = "staff_closed"
        return {"ok": True, "message": "Session closed"}

    _, session = await open_table_session(db, table_id)
    menu_url = f"{settings.frontend_url}/menu?t={table.qr_code_url}"
    return {
        "table_id": str(table.id),
        "table_number": table.table_number,
        "token": table.qr_code_url,
        "expires_at": session.expires_at.isoformat(),
        "menu_url": menu_url,
    }


@router.get("/tables")
async def list_tables(user: User = Depends(require_staff), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RestaurantTable).order_by(RestaurantTable.table_number))
    tables = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "table_number": t.table_number,
            "capacity": t.capacity,
            "qr_url": f"{settings.frontend_url}/menu?t={t.qr_code_url}" if t.qr_code_url else None,
        }
        for t in tables
    ]


@router.get("/customers")
async def list_customers(user: User = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    from app.models import UserRole

    result = await db.execute(select(User).where(User.role == UserRole.customer))
    customers = result.scalars().all()
    return [
        {"id": str(c.id), "name": c.name, "email": c.email, "loyalty_points": c.loyalty_points}
        for c in customers
    ]


@router.patch("/customers/{customer_id}/loyalty")
async def adjust_loyalty(
    customer_id: uuid.UUID,
    points: int,
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.loyalty_points = max(0, customer.loyalty_points + points)
    return {"loyalty_points": customer.loyalty_points}


@router.patch("/settings")
async def update_settings(
    data: SettingsUpdate,
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(RestaurantSettings).limit(1))
    restaurant = result.scalar_one_or_none()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Settings not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(restaurant, k, v)
    return {"ok": True}


@router.get("/staff")
async def list_staff(user: User = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    from app.models import UserRole
    result = await db.execute(select(User).where(User.role.in_([UserRole.staff, UserRole.owner])))
    staff = result.scalars().all()
    return [{"id": str(s.id), "name": s.name, "email": s.email, "role": s.role.value} for s in staff]


@router.post("/staff")
async def create_staff(
    data: StaffCreate,
    user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    from app.models import UserRole
    from app.core.security import hash_password
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    new_user = User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole(data.role),
    )
    db.add(new_user)
    await db.commit()
    return {"id": str(new_user.id), "name": new_user.name, "email": new_user.email, "role": new_user.role.value}


@router.delete("/staff/{user_id}")
async def delete_staff(
    user_id: uuid.UUID,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    result = await db.execute(select(User).where(User.id == user_id))
    staff_user = result.scalar_one_or_none()
    if not staff_user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(staff_user)
    await db.commit()
    return {"ok": True}
