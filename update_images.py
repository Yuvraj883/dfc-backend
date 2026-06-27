import asyncio
import os
from sqlalchemy import select
from app.db.session import async_session_maker
from app.models import MenuItem

IMAGES = {
    "burger": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?q=80&w=1500&auto=format&fit=crop",
    "bucket": "https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?q=80&w=1500&auto=format&fit=crop",
    "healthy": "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?q=80&w=1500&auto=format&fit=crop",
    "veg": "https://images.unsplash.com/photo-1550547660-d9450f859349?q=80&w=1500&auto=format&fit=crop",
    "wrap": "https://images.unsplash.com/photo-1626700051175-6818013e1d4f?q=80&w=1500&auto=format&fit=crop",
    "fries": "https://images.unsplash.com/photo-1576107232684-1279f3908581?q=80&w=1500&auto=format&fit=crop",
    "chicken": "https://images.unsplash.com/photo-1626082927389-6cd097cdc6ec?q=80&w=1500&auto=format&fit=crop",
    "shake": "https://images.unsplash.com/photo-1572490122747-3968b75bb8ef?q=80&w=1500&auto=format&fit=crop",
    "mojito": "https://images.unsplash.com/photo-1551538827-9c037cb4f32a?q=80&w=1500&auto=format&fit=crop",
    "coffee": "https://images.unsplash.com/photo-1461023058943-07fcbe16d735?q=80&w=1500&auto=format&fit=crop",
}

DEFAULT_IMAGE = "https://images.unsplash.com/photo-1604908176997-125f25cc6f3d?q=80&w=1500&auto=format&fit=crop"

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

SUPABASE_URL = "postgresql+asyncpg://postgres.swltevdruwdxpstlundb:YuvrajDFC88@aws-1-ap-northeast-2.pooler.supabase.com:6543/postgres"

async def main():
    print("Starting database image update against SUPABASE...")
    engine = create_async_engine(SUPABASE_URL, pool_pre_ping=True)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as db:
        result = await db.execute(select(MenuItem))
        items = result.scalars().all()
        
        updated_count = 0
        for item in items:
            name_lower = item.name.lower()
            matched_url = DEFAULT_IMAGE
            
            for key, url in IMAGES.items():
                if key in name_lower:
                    matched_url = url
                    break
            
            # Special case matching
            if "brost" in name_lower or "wings" in name_lower or "popcorn" in name_lower or "strips" in name_lower or "chizza" in name_lower:
                matched_url = IMAGES["chicken"]
            
            item.image_url = matched_url
            updated_count += 1
            
        await db.commit()
        print(f"Successfully updated {updated_count} menu items with Unsplash images!")

if __name__ == "__main__":
    asyncio.run(main())
