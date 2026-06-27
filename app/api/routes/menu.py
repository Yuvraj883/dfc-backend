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


import json
from fastapi.responses import JSONResponse
from app.core.redis import get_cache, set_cache

@router.get("", response_model=MenuResponse)
async def get_menu(
    vegetarian: bool | None = None,
    gluten_free: bool | None = None,
    spicy: bool | None = None,
    popular: bool | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    # Construct a deterministic cache key based on query parameters
    cache_key = f"menu_cache:v={vegetarian}:g={gluten_free}:s={spicy}:p={popular}:search={search}"
    
    # Try to fetch from Redis
    cached_data = await get_cache(cache_key)
    if cached_data:
        # Return the pre-serialized JSON directly for maximum speed
        return JSONResponse(content=json.loads(cached_data))

    # Fallback to database query
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

    response_obj = MenuResponse(
        categories=response_categories,
        global_customizations=[CustomizationResponse.model_validate(c) for c in global_customizations],
    )
    
    # Cache the result for 5 minutes (300 seconds)
    response_json = response_obj.model_dump_json()
    await set_cache(cache_key, response_json, expire_seconds=300)
    
    return response_obj


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
