import asyncio
from sqlalchemy import text, select
from app.db.session import engine
from app.models import RestaurantSettings

async def update_settings():
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE restaurant_settings SET max_reservations_per_slot = 1"))
    print("Successfully updated max_reservations_per_slot to 1 in the database.")

if __name__ == "__main__":
    asyncio.run(update_settings())
