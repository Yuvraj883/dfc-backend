from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models import ItemCustomization, MenuCategory, MenuItem
from app.schemas import CustomizationResponse, MenuCategoryResponse, MenuItemResponse, MenuResponse
from app.services.orders import get_global_customizations

router = APIRouter(prefix="/menu", tags=["menu"])


@router.get("", response_model=MenuResponse)
async def get_menu(
    vegetarian: bool | None = None,
    gluten_free: bool | None = None,
    spicy: bool | None = None,
    popular: bool | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MenuCategory)
        .options(selectinload(MenuCategory.items).selectinload(MenuItem.customizations))
        .order_by(MenuCategory.sort_order)
    )
    categories = result.scalars().all()
    global_customizations = await get_global_customizations(db)

    response_categories = []
    for cat in categories:
        items = []
        for item in cat.items:
            if not item.is_available:
                continue
            if vegetarian and not item.is_vegetarian:
                continue
            if gluten_free and not item.is_gluten_free:
                continue
            if spicy and item.spice_level < 2:
                continue
            if popular and not item.is_featured:
                continue
            if search and search.lower() not in item.name.lower():
                continue
            items.append(
                MenuItemResponse(
                    id=item.id,
                    category_id=item.category_id,
                    name=item.name,
                    description=item.description,
                    price=item.price,
                    image_url=item.image_url,
                    calories=item.calories,
                    allergens=item.allergens or [],
                    spice_level=item.spice_level,
                    is_vegetarian=item.is_vegetarian,
                    is_gluten_free=item.is_gluten_free,
                    is_available=item.is_available,
                    is_featured=item.is_featured,
                    customizations=[
                        CustomizationResponse.model_validate(c) for c in item.customizations
                    ],
                )
            )
        if items:
            response_categories.append(
                MenuCategoryResponse(
                    id=cat.id,
                    name=cat.name,
                    slug=cat.slug,
                    sort_order=cat.sort_order,
                    items=items,
                )
            )

    return MenuResponse(
        categories=response_categories,
        global_customizations=[CustomizationResponse.model_validate(c) for c in global_customizations],
    )


@router.get("/item/{item_id}", response_model=MenuItemResponse)
async def get_menu_item(item_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MenuItem).options(selectinload(MenuItem.customizations)).where(MenuItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return MenuItemResponse(
        id=item.id,
        category_id=item.category_id,
        name=item.name,
        description=item.description,
        price=item.price,
        image_url=item.image_url,
        calories=item.calories,
        allergens=item.allergens or [],
        spice_level=item.spice_level,
        is_vegetarian=item.is_vegetarian,
        is_gluten_free=item.is_gluten_free,
        is_available=item.is_available,
        is_featured=item.is_featured,
        customizations=[CustomizationResponse.model_validate(c) for c in item.customizations],
    )
