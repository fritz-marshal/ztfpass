"""ztfpass FastAPI app — the SkyPortal→ZTF-scheduler passthrough.

Replicates Kowalski's `/api/triggers/ztf` (GET/PUT/DELETE) + `/api/triggers/
ztf.test`, including the response envelope `{status, message, data}` and the
status-code semantics SkyPortal expects, so it is a drop-in replacement for the
one Kowalski capability still in use.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .config import Settings, load_settings
from .models import ZTFDelete, ZTFTrigger
from .scheduler import SSHTunnelSchedulerClient, SchedulerClient


def _ok(message: str, data: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=200, content={"status": "success", "message": message, "data": data}
    )


def _err(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"status": "error", "message": message}
    )


def create_app(
    settings: Settings | None = None, client: SchedulerClient | None = None
) -> FastAPI:
    settings = settings or load_settings()
    client = client or SSHTunnelSchedulerClient(
        settings.ztf, path=settings.scheduler_path, timeout=settings.scheduler_timeout
    )
    app = FastAPI(title="ztfpass", version="0.1.0")

    def require_token(authorization: str | None = Header(default=None)) -> None:
        # Match SkyPortal: it sends `Authorization: Bearer <access_token>`.
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        token = authorization[len("Bearer ") :].strip()
        if not settings.tokens or token not in settings.tokens:
            raise HTTPException(status_code=401, detail="invalid token")

    @app.exception_handler(HTTPException)
    async def _http_exc(_request: Request, exc: HTTPException):
        # Keep the {status, message} envelope even for auth errors.
        return JSONResponse(
            status_code=exc.status_code,
            content={"status": "error", "message": exc.detail},
        )

    @app.get("/healthz")
    async def healthz():
        return {
            "status": "success",
            "message": "ok",
            "data": {"tunnel_configured": settings.ztf.complete()},
        }

    @app.get("/api/triggers/ztf", dependencies=[Depends(require_token)])
    async def get_queue():
        res = client.forward("GET", {})
        if res.status == 200:
            return _ok("retrieved", data=res.json)
        return _err(f"ZTF queue query attempt rejected: {res.json}")

    @app.put("/api/triggers/ztf", dependencies=[Depends(require_token)])
    async def put_queue(request: Request):
        body = await request.json()
        try:
            ZTFTrigger(**body)
        except ValidationError as e:
            return _err(f"invalid trigger payload: {e}", status=400)

        res = client.forward("PUT", body)
        if res.status == 201:
            return _ok("submitted", data=res.headers)
        if res.status == 200:
            qn = res.headers.get("queue_name", body.get("queue_name", "?"))
            return _err(f"Submitted queue {qn} already exists", status=409)
        return _err(f"ZTF trigger attempt rejected: {res.json}")

    @app.delete("/api/triggers/ztf", dependencies=[Depends(require_token)])
    async def delete_queue(request: Request):
        body = await request.json()
        try:
            ZTFDelete(**body)
        except ValidationError as e:
            return _err(f"invalid delete payload: {e}", status=400)

        res = client.forward("DELETE", body)
        if res.status == 200:
            return _ok("deleted", data=res.headers)
        return _err(f"ZTF delete attempt rejected: {res.json}")

    @app.put("/api/triggers/ztf.test", dependencies=[Depends(require_token)])
    async def put_queue_test(request: Request):
        # Validate but never forward — same as Kowalski's ztf.test route.
        body = await request.json()
        try:
            ZTFTrigger(**body)
        except ValidationError as e:
            return _err(f"invalid trigger payload: {e}", status=400)
        return _ok("submitted")

    return app
