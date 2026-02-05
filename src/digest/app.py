from fastapi import FastAPI

from digest.routes.digests import router as digests_router
from digest.routes.inbound import router as inbound_router


def create_app() -> FastAPI:
    app = FastAPI(title="Morning Digest API", version="0.1.0")

    app.include_router(inbound_router)
    app.include_router(digests_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
