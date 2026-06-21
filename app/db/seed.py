import uuid

from sqlalchemy import select

from app.core.security import generate_opaque_token, hash_password, hash_token
from app.db.session import async_session_maker
from app.models import (
    DiscountType,
    ItemCustomization,
    MenuCategory,
    MenuItem,
    PromoCode,
    RestaurantSettings,
    RestaurantTable,
    Review,
    User,
    UserRole,
)

DEFAULT_HOURS = {
    "monday": {"open": "11:00", "close": "23:00"},
    "tuesday": {"open": "11:00", "close": "23:00"},
    "wednesday": {"open": "11:00", "close": "23:00"},
    "thursday": {"open": "11:00", "close": "23:00"},
    "friday": {"open": "11:00", "close": "23:00"},
    "saturday": {"open": "11:00", "close": "23:00"},
    "sunday": {"open": "11:00", "close": "23:00"},
}

MENU_DATA = [
    ("burger-hub", "Burger Hub", [
        ("DFC Classic Chicken Burger", 80, False, 1),
        ("DFC Chicken Cheese Burger", 90, False, 1),
        ("DFC Tandoori Hot Burger", 100, False, 2),
        ("DFC Classic Wonder Burger", 110, False, 1),
        ("DFC Maharaja Burger", 140, False, 2),
    ]),
    ("bucket-hub", "Bucket Hub", [
        ("DFC Classic Bucket (4pc)", 249, False, 0),
        ("DFC Classic Bucket Brost (6pc)", 299, False, 0),
    ]),
    ("healthy-hub", "Healthy Hub", [
        ("DFC Boiled Chicken (Half)", 120, False, 0),
        ("DFC Boiled Chicken (Full)", 180, False, 0),
        ("DFC Diet Chicken Sandwich", 100, False, 0),
        ("DFC Diet Salad (Half)", 120, True, 0),
        ("DFC Diet Salad (Full)", 130, True, 0),
        ("DFC Diet Sub", 120, False, 0),
    ]),
    ("veg-hub", "Veg Hub", [
        ("DFC Veg Crunch Burger", 50, True, 1),
        ("DFC Veg Cheese Crunch Burger", 60, True, 1),
        ("DFC Veg Tandoori Burger", 70, True, 2),
        ("DFC Veg Wonder Burger", 80, True, 1),
        ("DFC Paneer Wonder Burger", 110, True, 1),
        ("DFC Paneer Burger", 90, True, 1),
        ("DFC Paneer Tandoori Burger", 100, True, 2),
    ]),
    ("veg-wrap-sandwich", "Veg Wrap & Sandwich", [
        ("DFC Classic Cheese Paneer Sandwich", 90, True, 0),
        ("DFC Veg Wrap with Cheese", 100, True, 1),
        ("DFC Paneer Wrap with Cheese", 120, True, 1),
    ]),
    ("sides-snacks-mains", "Sides, Snacks & Mains", [
        ("Chicken Lollipop (Half)", 120, False, 2),
        ("Chicken Lollipop (Full)", 130, False, 2),
        ("Chicken Popcorn", 120, False, 1),
        ("Boneless Strips (Half)", 120, False, 1),
        ("Boneless Strips (Full)", 150, False, 1),
        ("Boneless Brost (Half)", 120, False, 1),
        ("Boneless Brost (Full)", 150, False, 1),
        ("Hot Wings (Half)", 100, False, 3),
        ("Hot Wings (Full)", 150, False, 3),
        ("Chicken Wings", 100, False, 2),
        ("Chicken Chizza Roll", 150, False, 1),
        ("Grilled Chicken Sandwich", 80, False, 0),
        ("Chizza", 180, False, 1),
        ("French Fries", 60, True, 0),
        ("Peri-Peri Fries", 80, True, 1),
        ("Cheesy Fries", 100, True, 0),
        ("DFC Chicken Cheesy Fries", 249, False, 0),
        ("DFC Classic Combo", 379, False, 0),
        ("DFC Brost Sub", 130, False, 1),
        ("Paneer Chizza Roll", 150, True, 1),
        ("DFC Shawarma", 100, False, 1),
    ]),
    ("beverages", "Beverages", [
        ("DFC Hazelnut Shake", 99, True, 0),
        ("DFC Mojito", 80, True, 0),
        ("DFC Classic Cold Coffee", 80, True, 0),
    ]),
]

FEATURED = {
    "DFC Classic Chicken Burger",
    "DFC Classic Bucket (4pc)",
    "Hot Wings (Full)",
    "DFC Classic Combo",
    "DFC Hazelnut Shake",
}


async def seed_database() -> None:
    async with async_session_maker() as db:
        existing = await db.execute(select(MenuCategory).limit(1))
        if existing.scalar_one_or_none():
            return

        owner = User(
            name="DFC Owner",
            email="owner@dfc.com",
            password_hash=hash_password("owner12345"),
            role=UserRole.owner,
        )
        staff = User(
            name="DFC Staff",
            email="staff@dfc.com",
            password_hash=hash_password("staff12345"),
            role=UserRole.staff,
        )
        db.add_all([owner, staff])

        settings_row = RestaurantSettings(
            name="Delhi Fried Chicken",
            tagline="The Capital of Crisp.",
            address="C4E, Main Market, Janakpuri (near Mother Dairy), New Delhi",
            phone="9289912765",
            email="hello@delhifriedchicken.com",
            lat=28.6219,
            lng=77.0878,
            hours=DEFAULT_HOURS,
            banner_text="Welcome to Delhi Fried Chicken!",
            announcement=None,
            max_reservations_per_slot=5,
        )
        db.add(settings_row)

        cheese = ItemCustomization(
            name="Extra Cheese Slice",
            customization_type="single",
            options={"label": "Add extra cheese slice"},
            extra_price=20,
            is_global=True,
        )
        dip = ItemCustomization(
            name="Add Dip",
            customization_type="single",
            options={"label": "Any dip"},
            extra_price=20,
            is_global=True,
        )
        db.add_all([cheese, dip])

        sort_cat = 0
        for slug, name, items in MENU_DATA:
            cat = MenuCategory(name=name, slug=slug, sort_order=sort_cat)
            db.add(cat)
            await db.flush()
            sort_cat += 1

            for idx, (item_name, price, is_veg, spice) in enumerate(items):
                db.add(
                    MenuItem(
                        category_id=cat.id,
                        name=item_name,
                        description=f"Delicious {item_name} from DFC's {name} — made fresh to order.",
                        price=price,
                        image_url=None,
                        calories=None,
                        allergens=["gluten"] if "Burger" in item_name or "Sandwich" in item_name else [],
                        spice_level=spice,
                        is_vegetarian=is_veg,
                        is_gluten_free=False,
                        is_available=True,
                        is_featured=item_name in FEATURED,
                        sort_order=idx,
                    )
                )

        for i in range(1, 16):
            qr_token = generate_opaque_token()
            db.add(
                RestaurantTable(
                    table_number=i,
                    capacity=4,
                    qr_code_url=qr_token,
                )
            )

        db.add(
            PromoCode(
                code="DFC10",
                discount_type=DiscountType.percent,
                discount_value=10,
                usage_limit=100,
                per_user_limit=1,
            )
        )
        db.add(
            PromoCode(
                code="WELCOME50",
                discount_type=DiscountType.fixed,
                discount_value=50,
                usage_limit=50,
                per_user_limit=1,
            )
        )

        reviews = [
            ("Rahul S.", 5, "Best fried chicken in Janakpuri! The Maharaja Burger is incredible."),
            ("Priya M.", 5, "Love the crispy buckets. Quick service and great value."),
            ("Amit K.", 4, "Hot wings are spicy and perfect. Will definitely come back."),
            ("Neha G.", 5, "Family-friendly spot with amazing combos. The Capital of Crisp lives up to its name!"),
        ]
        for name, rating, comment in reviews:
            db.add(Review(customer_name=name, rating=rating, comment=comment, source="curated"))

        await db.commit()
