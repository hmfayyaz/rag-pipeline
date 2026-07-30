import asyncio
import click
from app.commands import command, info, success, error
from app.db.session import get_db_context
from app.services.dev_seeding import DevSeedingService


@command("seed-demo", help="Wipe database and seed a complete multi-tenant demo setup")
def seed_demo() -> None:
    """Wipe current data and generate a fully-fledged multi-tenant environment.
    
    Creates:
    - Tenant A & Tenant B organizations
    - Users for every role (owner, admin, member, viewer) in each tenant
    - 20 documents in each tenant with various departments, confidentiality, and access permissions
    """
    async def _run():
        async with get_db_context() as db:
            seeder = DevSeedingService(db)
            info("Starting development demo seeding...")
            results = await seeder.seed_demo_data()
            success("Demo data seeded successfully!")
            
            # Print report of generated entities
            info("\n--- Generated Tenants ---")
            for name, tid in results["tenants"].items():
                info(f"- {name}: ID={tid}")
            
            info("\n--- Login Credentials (password: password123) ---")
            for name, roles in results["users"].items():
                info(f"\n{name}:")
                for role, user in roles.items():
                    info(f"  - {role.capitalize()}: email={user['email']}, user_id={user['id']}")

    try:
        asyncio.run(_run())
    except Exception as e:
        error(f"Error during seeding: {e}")
