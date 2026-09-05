# handlers/__init__.py
from .start import router as start_router
from .about_service import router as about_service_router
from .help import router as help_router
from .payment import router as payment_router
from .profile import router as profile_router
from .admin_web import router as admin_router

__all__ = [
    "start_router", 
    "about_service_router",
    "help_router",
    "payment_router", 
    "profile_router", 
    "admin_router"
]