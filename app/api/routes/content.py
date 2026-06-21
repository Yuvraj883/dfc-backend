from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import CateringInquiry, ContactMessage, RestaurantSettings, Review
from app.schemas import CateringRequest, ContactRequest, ReviewResponse, SettingsResponse

router = APIRouter(tags=["content"])


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RestaurantSettings).limit(1))
    settings = result.scalar_one_or_none()
    return settings


@router.get("/reviews", response_model=list[ReviewResponse])
async def get_reviews(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Review).where(Review.is_published.is_(True)).order_by(Review.created_at.desc())
    )
    return result.scalars().all()


@router.post("/catering")
async def submit_catering(data: CateringRequest, db: AsyncSession = Depends(get_db)):
    inquiry = CateringInquiry(**data.model_dump())
    db.add(inquiry)
    return {"ok": True, "message": "We'll contact you within 24 hours"}


@router.post("/contact")
async def submit_contact(data: ContactRequest, db: AsyncSession = Depends(get_db)):
    message = ContactMessage(**data.model_dump())
    db.add(message)
    return {"ok": True, "message": "Thank you for your message"}
