import asyncio
from sqlalchemy import text
from app.db.session import engine

async def check():
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT date, time, email, name FROM reservations"))
        rows = res.fetchall()
        print(f"Total reservations: {len(rows)}")
        for r in rows:
            print(r)

if __name__ == "__main__":
    asyncio.run(check())
