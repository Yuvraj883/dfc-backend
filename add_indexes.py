import asyncio
from sqlalchemy import text
from app.db.session import engine

async def add_indexes():
    print("Creating database indexes...")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_role ON users (role);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_menu_items_category_id ON menu_items (category_id);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_item_customizations_menu_item_id ON item_customizations (menu_item_id);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_user_id ON orders (user_id);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_status ON orders (status);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_created_at ON orders (created_at);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reservations_date ON reservations (date);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reviews_is_published ON reviews (is_published);"))
    print("Indexes added successfully.")

if __name__ == "__main__":
    asyncio.run(add_indexes())
