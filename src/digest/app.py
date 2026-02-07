from fastapi import FastAPI

from digest.routes.admin import router as admin_router
from digest.routes.auth import router as auth_router
from digest.routes.digests import router as digests_router
from digest.routes.inbound import router as inbound_router
from digest.routes.sources import router as sources_router
from digest.routes.users import router as users_router


def create_app() -> FastAPI:
    app = FastAPI(title="Morning Digest API", version="0.1.0")

    app.include_router(auth_router)
    app.include_router(inbound_router)
    app.include_router(digests_router)
    app.include_router(sources_router)
    app.include_router(users_router)
    app.include_router(admin_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
