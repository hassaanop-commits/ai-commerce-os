from fastapi import APIRouter

from app.api.v1.ai import router as ai_router
from app.api.v1.auth import router as auth_router
from app.api.v1.listings import router as listings_router
from app.api.v1.marketplace_connections import router as marketplace_connections_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.products import router as products_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(organizations_router)
router.include_router(products_router)
router.include_router(ai_router)
router.include_router(marketplace_connections_router)
router.include_router(listings_router)


@router.get("/ping")
def ping():
    return {"message": "pong"}
