from fastapi import APIRouter

from app.api.routers.auth import router as auth_router
from app.api.routers.dashboard import router as dashboard_router
from app.api.routers.employees import router as employees_router
from app.api.routers.face_enrollments import router as face_enrollments_router
from app.api.routers.organizations import router as organizations_router
from app.api.routers.organizational_units import router as organizational_units_router
from app.api.routers.presences import router as presences_router
from app.api.routers.recognitions import router as recognitions_router
from app.api.routers.system import router as system_router
from app.api.routers.user_accounts import router as user_accounts_router
from app.api.routers.visitors import router as visitors_router
from app.api.routers.visits import router as visits_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(user_accounts_router)
api_router.include_router(organizations_router)
api_router.include_router(organizational_units_router)
api_router.include_router(employees_router)
api_router.include_router(visitors_router)
api_router.include_router(visits_router)
api_router.include_router(face_enrollments_router)
api_router.include_router(recognitions_router)
api_router.include_router(presences_router)
api_router.include_router(dashboard_router)
api_router.include_router(system_router)
