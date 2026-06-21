from uuid import UUID
from datetime import date, datetime, time
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# Auth
class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(ORMModel):
    id: UUID
    name: str
    email: str
    phone: Optional[str]
    role: str
    loyalty_points: int


class StaffCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str


# Menu
class CustomizationResponse(ORMModel):
    id: UUID
    name: str
    customization_type: str
    options: dict
    extra_price: float
    is_global: bool


class MenuItemResponse(ORMModel):
    id: UUID
    category_id: UUID
    name: str
    description: Optional[str]
    price: float
    image_url: Optional[str]
    calories: Optional[int]
    allergens: list[str]
    spice_level: int
    is_vegetarian: bool
    is_gluten_free: bool
    is_available: bool
    is_featured: bool
    customizations: list[CustomizationResponse] = []


class MenuCategoryResponse(ORMModel):
    id: UUID
    name: str
    slug: str
    sort_order: int
    items: list[MenuItemResponse] = []


class MenuResponse(BaseModel):
    categories: list[MenuCategoryResponse]
    global_customizations: list[CustomizationResponse] = []


# Orders
class OrderItemRequest(BaseModel):
    menu_item_id: UUID
    quantity: int = Field(ge=1, le=50)
    customization_ids: list[UUID] = []


class CreateOrderRequest(BaseModel):
    order_type: str
    items: list[OrderItemRequest]
    promo_code: Optional[str] = None
    tip: float = Field(ge=0, default=0)
    payment_method: str = "stripe"
    pickup_time: Optional[datetime] = None
    guest_name: Optional[str] = None
    guest_email: Optional[EmailStr] = None
    guest_phone: Optional[str] = None
    loyalty_points_redeem: int = Field(ge=0, default=0)


class OrderItemResponse(ORMModel):
    id: UUID
    item_name: str
    quantity: int
    selected_customizations: dict
    line_price: float


class OrderResponse(ORMModel):
    id: UUID
    order_type: str
    status: str
    subtotal: float
    tax: float
    discount: float
    tip: float
    total: float
    payment_status: str
    pickup_time: Optional[datetime]
    loyalty_points_earned: int
    created_at: datetime
    items: list[OrderItemResponse]
    guest_token: Optional[str] = None


# Reservations
class CreateReservationRequest(BaseModel):
    name: str = Field(min_length=2)
    phone: str
    email: EmailStr
    party_size: int = Field(ge=1, le=20)
    date: date
    time: time
    special_requests: Optional[str] = None


class AvailabilitySlot(BaseModel):
    time: str
    available: bool
    remaining: int


class AvailabilityResponse(BaseModel):
    date: date
    slots: list[AvailabilitySlot]


class ReservationResponse(ORMModel):
    id: UUID
    name: str
    phone: str
    email: str
    party_size: int
    date: date
    time: time
    status: str
    special_requests: Optional[str]
    cancel_token: Optional[str] = None


# Promo
class ValidatePromoRequest(BaseModel):
    code: str
    subtotal: float


class ValidatePromoResponse(BaseModel):
    valid: bool
    discount: float = 0
    message: str = ""


# Reviews & content
class ReviewResponse(ORMModel):
    id: UUID
    customer_name: str
    rating: int
    comment: str
    source: str
    created_at: datetime


class SettingsResponse(ORMModel):
    name: str
    tagline: str
    address: str
    phone: str
    email: str
    lat: float
    lng: float
    hours: dict
    holiday_closures: list
    banner_text: Optional[str]
    announcement: Optional[str]


class CateringRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str
    event_date: Optional[date] = None
    guest_count: Optional[int] = None
    message: str


class ContactRequest(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str


# Admin
class MenuItemCreate(BaseModel):
    category_id: UUID
    name: str
    description: Optional[str] = None
    price: float = Field(gt=0)
    calories: Optional[int] = None
    allergens: list[str] = []
    spice_level: int = 0
    is_vegetarian: bool = False
    is_gluten_free: bool = False
    is_available: bool = True
    is_featured: bool = False


class MenuItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    is_available: Optional[bool] = None
    is_featured: Optional[bool] = None


class OrderStatusUpdate(BaseModel):
    status: str


class ReservationStatusUpdate(BaseModel):
    status: str


class PromoCodeCreate(BaseModel):
    code: str
    discount_type: str
    discount_value: float
    expires_at: Optional[datetime] = None
    usage_limit: Optional[int] = None
    per_user_limit: int = 1


class SettingsUpdate(BaseModel):
    banner_text: Optional[str] = None
    announcement: Optional[str] = None
    hours: Optional[dict] = None


class DashboardStats(BaseModel):
    today_orders: int
    today_revenue: float
    today_reservations: int
    pending_orders: int
    popular_items: list[dict[str, Any]]


class TableSessionResponse(BaseModel):
    table_id: UUID
    table_number: int
    token: str
    expires_at: datetime
    menu_url: str


class PaymentIntentResponse(BaseModel):
    client_secret: str
    payment_intent_id: str
    mock: bool = True
