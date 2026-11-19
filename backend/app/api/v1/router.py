from fastapi import APIRouter

from app.api.v1.analytics import admin_router as analytics_admin_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.audit import router as audit_router
from app.api.v1.auth import admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.channels import sms_router, ussd_router
from app.api.v1.directory import admin_router as directory_admin_router
from app.api.v1.directory import router as directory_router
from app.api.v1.evidence import router as evidence_router
from app.api.v1.health import router as health_router
from app.api.v1.incidents import public_router as public_incidents_router
from app.api.v1.incidents import router as incidents_router
from app.api.v1.register import router as register_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(admin_router)
router.include_router(audit_router)
router.include_router(directory_router)
router.include_router(directory_admin_router)
router.include_router(register_router)
router.include_router(evidence_router)
router.include_router(analytics_router)
router.include_router(analytics_admin_router)
router.include_router(incidents_router)
router.include_router(public_incidents_router)
router.include_router(ussd_router)
router.include_router(sms_router)
