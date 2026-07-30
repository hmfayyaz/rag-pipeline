import asyncio
import click
from app.commands import command, info, success, error
from app.db.session import get_db_context
from app.services.dev_seeding import DevSeedingService


@command("reset-demo", help="Wipe all users, orgs, documents, conversations, and vector indices")
def reset_demo() -> None:
    """Wipe all conversations, users (except app admins), files, organizations, and vector indexes."""
    async def _run():
        async with get_db_context() as db:
            seeder = DevSeedingService(db)
            info("Resetting development database and vector store...")
            await seeder.reset_everything()
            success("Environment reset successfully!")

    try:
        asyncio.run(_run())
    except Exception as e:
        error(f"Error during database reset: {e}")
