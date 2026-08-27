"""
WeCare FastAPI — Application Entry Point

Each endpoint file includes response + cors.
FastAPI centralizes this in a single application object with middleware.

Phase 2: FastAPI startup + health endpoint
Phase 3: Auth routes + APIException handler
"""

import datetime
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.constants import ALLOWED_ENVIRONMENTS, APP_NAME, APP_VERSION, API_BASE_PATH
from app.core.exceptions import APIException, api_exception_handler

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    Application factory.
    Creates and configures the FastAPI instance.
    """
    settings = get_settings()

    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        docs_url="/api/v1/docs" if settings.APP_ENV != "production" else None,
        redoc_url="/api/v1/redoc" if settings.APP_ENV != "production" else None,
        openapi_url="/api/v1/openapi.json" if settings.APP_ENV != "production" else None,
    )

    # ── CORS Middleware ──
    # config/cors → send_cors_headers()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|.*\.railway\.app|.*\.up\.railway\.app)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
        max_age=86400,
    )

    # ── Static Files (Uploads) ──
    import os
    from fastapi.staticfiles import StaticFiles

    upload_path = os.path.join(os.getcwd(), settings.UPLOAD_BASE_PATH)
    for sub in ["profiles", "caretaker_docs", "complaints"]:
        os.makedirs(os.path.join(upload_path, sub), exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=upload_path), name="uploads")

    # ── APIException Handler (Phase 3) ──
    # Custom exception → standard error envelope
    app.add_exception_handler(APIException, api_exception_handler)

    # ── Global Exception Handler ──
    # response shutdown handler that catches E_ERROR
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal server error",
                "data": None,
                "errors": None,
            },
        )

    # ── Health & Root Endpoints ──
    @app.get("/")
    def root():
        """Root status ping for Railway live deployments."""
        return {
            "success": True,
            "message": "WeCare API is live and operational",
            "app": APP_NAME,
            "version": APP_VERSION,
            "environment": settings.APP_ENV,
            "health": "/api/v1/health",
            "docs": "/api/v1/docs" if settings.APP_ENV != "production" else None,
        }

    @app.get("/health")
    def health_root():
        """Platform healthcheck alias."""
        return health()

    # api/v1/health (GET only, no auth)
    @app.get("/api/v1/health")
    def health():
        """
        Exact reproduction of api/v1/health response.
        """
        environment = settings.APP_ENV
        if environment not in ALLOWED_ENVIRONMENTS:
            environment = "production"

        return {
            "success": True,
            "message": "API is reachable",
            "data": {
                "app": APP_NAME,
                "environment": environment,
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "version": APP_VERSION,
                "api_base_path": API_BASE_PATH,
            },
            "errors": None,
        }

    # ── Auth Routes (Phase 3 & 4) ──
    from app.api.v1.auth.login import router as login_router
    from app.api.v1.auth.logout import router as logout_router
    from app.api.v1.auth.refresh import router as refresh_router
    from app.api.v1.auth.register import router as register_router
    from app.api.v1.auth.password import router as password_router
    from app.api.v1.auth.forgot_password import router as forgot_password_router
    from app.api.v1.auth.profile import router as profile_router

    # ── Phase 4, 5, 6, 7, 8, 9, 10 & 11 Routes ──
    from app.api.v1.patient.router import router as patient_router
    from app.api.v1.caretaker.router import router as caretaker_router
    from app.api.v1.admin.router import router as admin_router
    from app.api.v1.booking.router import router as booking_router
    from app.api.v1.visit.router import router as visit_router
    from app.api.v1.sos.router import router as sos_router
    from app.api.v1.review.router import router as review_router
    from app.api.v1.complaint.router import router as complaint_router
    from app.api.v1.replacement.router import router as replacement_router
    from app.api.v1.replacement_tickets import replacement_tickets_router
    from app.api.v1.notification.router import router as notification_router
    from app.api.v1.payment.router import router as payment_router
    from app.api.v1.checklist.router import router as checklist_router
    from app.api.v1.dashboard.router import router as dashboard_router
    from app.api.v1.system.router import router as system_router

    app.include_router(login_router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(logout_router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(refresh_router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(register_router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(password_router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(forgot_password_router, prefix="/api/v1/auth/forgot-password", tags=["auth"])
    app.include_router(profile_router, prefix="/api/v1/auth", tags=["auth", "profile"])

    app.include_router(patient_router, prefix="/api/v1/patient", tags=["patient"])
    app.include_router(caretaker_router, prefix="/api/v1/caretaker", tags=["caretaker"])
    app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(booking_router, prefix="/api/v1/booking", tags=["booking"])
    app.include_router(visit_router, prefix="/api/v1/visit", tags=["visit"])
    app.include_router(sos_router, prefix="/api/v1/sos", tags=["sos"])
    app.include_router(review_router, prefix="/api/v1/review", tags=["review"])
    app.include_router(complaint_router, prefix="/api/v1/complaint", tags=["complaint"])
    app.include_router(replacement_router, prefix="/api/v1/replacement", tags=["replacement"])
    app.include_router(replacement_tickets_router, prefix="/api/v1/replacement_tickets", tags=["replacement_tickets"])
    app.include_router(notification_router, prefix="/api/v1/notification", tags=["notification"])
    app.include_router(payment_router, prefix="/api/v1/payment", tags=["payment"])
    app.include_router(checklist_router, prefix="/api/v1/checklist", tags=["checklist"])
    app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["dashboard"])
    app.include_router(system_router, prefix="/api/v1/system", tags=["system"])

    # ── Startup Event ──
    @app.on_event("startup")
    def on_startup():
        # Import models to register them with Base.metadata
        import app.models  # noqa: F401
        from app.db.init_db import auto_init_database
        logger.info(f"WeCare API starting in '{settings.APP_ENV}' mode")
        try:
            auto_init_database()
        except Exception as e:
            logger.warning(f"Startup DB check notice: {e}")

    return app


# Module-level app instance for uvicorn
app = create_app()
