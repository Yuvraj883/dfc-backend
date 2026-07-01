import asyncio
from datetime import date, time
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import async_session_maker
from app.services.orders import get_availability, create_reservation
from app.schemas import CreateReservationRequest

async def test_booking():
    async with async_session_maker() as db:
        print("Initial availability:")
        slots = await get_availability(db, date(2026, 7, 1))
        print([s for s in slots if s["time"] == "11:00"])
        
        print("\nCreating reservation at 11:00...")
        req = CreateReservationRequest(
            name="Test User",
            email="test@example.com",
            phone="1234567890",
            party_size=2,
            date=date(2026, 7, 1),
            time=time(11, 0),
            special_requests="None"
        )
        try:
            res = await create_reservation(db, req, None)
            await db.commit()
            print("Reservation created successfully!")
        except Exception as e:
            print("Failed to create:", e)
            await db.rollback()
            
        print("\nAvailability after booking:")
        slots = await get_availability(db, date(2026, 7, 1))
        print([s for s in slots if s["time"] == "11:00"])

if __name__ == "__main__":
    asyncio.run(test_booking())
