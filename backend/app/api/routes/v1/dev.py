from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.config import settings
from app.services.dev_seeding import DevSeedingService

router = APIRouter()


def check_dev_environment():
    """Verify that development seed/reset endpoints are only accessible in development environments."""
    if settings.ENVIRONMENT not in ("local", "development"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev seeding operations are restricted to local/development environments."
        )


@router.post("/seed", status_code=status.HTTP_201_CREATED, dependencies=[Depends(check_dev_environment)])
async def seed_development_data(db: AsyncSession = Depends(get_db_session)):
    """Wipe current data and generate a fully-fledged multi-tenant environment.
    
    Creates:
    - Tenant A & Tenant B organizations
    - Users for every role (owner, admin, member, viewer) in each tenant
    - 20 documents in each tenant with various departments, confidentiality, and access permissions
    """
    seeder = DevSeedingService(db)
    try:
        results = await seeder.seed_demo_data()
        return {
            "status": "success",
            "message": "Development database and vector store seeded successfully.",
            "data": results
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to seed development data: {str(e)}"
        )


@router.post("/reset", status_code=status.HTTP_200_OK, dependencies=[Depends(check_dev_environment)])
async def reset_development_data(db: AsyncSession = Depends(get_db_session)):
    """Wipe all conversations, users (except app admins), files, organizations, and vector indexes."""
    seeder = DevSeedingService(db)
    try:
        await seeder.reset_everything()
        return {
            "status": "success",
            "message": "Development database and vector indexes cleared successfully."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset development data: {str(e)}"
        )
