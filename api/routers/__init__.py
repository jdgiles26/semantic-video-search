"""
API router modules.
"""
from .search import router as search_router
from .cameras import router as cameras_router
from .tasks import router as tasks_router
from .assets import router as assets_router
from .alerts import router as alerts_router
from .ai import router as ai_router
from .live import router as live_router
from .opord import router as opord_router

__all__ = [
    "search_router",
    "cameras_router",
    "tasks_router",
    "assets_router",
    "alerts_router",
    "ai_router",
    "live_router",
    "opord_router",
]
