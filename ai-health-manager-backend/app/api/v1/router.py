"""API v1 router."""

from fastapi import APIRouter

from app.api.v1 import agents, auth_routes, chat_routes, health, knowledge

router = APIRouter(prefix="/v1")

# Include routers
router.include_router(chat_routes.router, prefix="/chat", tags=["chat"])
router.include_router(agents.router, tags=["agents"])
router.include_router(auth_routes.router)
router.include_router(health.router)
router.include_router(knowledge.router)


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0"}


@router.get("/agents")
async def list_agents():
    """List all available agents."""
    from app.agents.registry import agent_registry

    return {
        "agents": agent_registry.get_info()
    }
