"""API v1 router aggregation."""
# ruff: noqa: I001 - Imports structured for Jinja2 template conditionals

from fastapi import APIRouter

from app.api.routes.v1 import health
from app.api.routes.v1 import admin_users, auth, users
from app.api.routes.v1 import admin_ratings
from app.api.routes.v1 import conversations, public_demos
from app.api.routes.v1 import admin_conversations
from app.api.routes.v1 import agent
from app.api.routes.v1 import rag
from app.api.routes.v1 import files
from app.api.routes.v1 import members, organizations
from app.api.routes.v1.invitations import (
    org_router as invitations_org_router,
    token_router as invitations_token_router,
)
from app.api.routes.v1 import knowledge_bases
from app.api.routes.v1 import me_slash_commands
from app.api.routes.v1 import admin_stats
from app.api.routes.v1 import org_integrations
from app.api.routes.v1 import dev

v1_router = APIRouter()

v1_router.include_router(health.router, tags=["health"])
v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])
v1_router.include_router(users.router, prefix="/users", tags=["users"])

# Hide generic/admin templates from Swagger UI but keep active for backend test suite
v1_router.include_router(
    admin_ratings.router, prefix="/admin/ratings", tags=["admin:ratings"], include_in_schema=False
)
v1_router.include_router(
    conversations.router, prefix="/conversations", tags=["conversations"], include_in_schema=False
)
v1_router.include_router(
    public_demos.router, prefix="/demos", tags=["demos"], include_in_schema=False
)
v1_router.include_router(
    agent.router, tags=["agent"], include_in_schema=False
)

v1_router.include_router(rag.router, prefix="/rag", tags=["rag"])

v1_router.include_router(
    files.router, tags=["files"], include_in_schema=False
)
v1_router.include_router(
    admin_conversations.router, prefix="/admin/conversations", tags=["admin-conversations"], include_in_schema=False
)
v1_router.include_router(
    admin_users.router, prefix="/admin/users", tags=["admin:users"], include_in_schema=False
)
v1_router.include_router(
    organizations.router, prefix="/orgs", tags=["organizations"], include_in_schema=False
)
v1_router.include_router(
    members.router, prefix="/orgs", tags=["members"], include_in_schema=False
)
v1_router.include_router(
    invitations_org_router, prefix="/orgs", tags=["invitations"], include_in_schema=False
)
v1_router.include_router(
    invitations_token_router, tags=["invitations"], include_in_schema=False
)
v1_router.include_router(
    knowledge_bases.router, prefix="/kb", tags=["knowledge-bases"], include_in_schema=False
)
v1_router.include_router(
    me_slash_commands.router, prefix="/me/slash-commands", tags=["me:slash-commands"], include_in_schema=False
)
v1_router.include_router(
    admin_stats.router, prefix="/admin", tags=["admin:stats"], include_in_schema=False
)
v1_router.include_router(
    org_integrations.router, prefix="/org/integrations", tags=["org:integrations"], include_in_schema=False
)

v1_router.include_router(dev.router, prefix="/dev", tags=["dev"])
