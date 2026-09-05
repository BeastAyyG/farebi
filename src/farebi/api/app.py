"""FastAPI surface for the reviewer console (Phase 08, first slice).

* ``GET /v1/health`` - liveness + served signal list, no image needed.
* ``POST /v1/detect`` - multipart ``file`` upload -> :func:`service.detect_image`.

Error contract (mirrors ``frontend/src/api/client.ts``):

* 4xx returns ``{"detail": <A.9 copy>}`` which the client renders verbatim.
* Anything unexpected returns the fixed A.9 500 copy; the traceback stays in
  the server log and never reaches the reviewer.

Run locally::

    .venv/Scripts/python.exe -m uvicorn farebi.api.app:app --port 8000

Layer: L8 api.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

from farebi.api import service

log = logging.getLogger(__name__)

_UNEXPECTED: str = "An unexpected error occurred. Please try again."


def create_app() -> FastAPI:
    """Application factory (keeps import side-effect free for tests)."""
    app = FastAPI(title="Farebi KYC detector", version=service.MODEL_VERSION)

    @app.get("/v1/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "model_version": service.MODEL_VERSION,
            "threshold_version": service._threshold_version(),
            "signals": service.list_signal_names(),
        }

    @app.post("/v1/detect")
    async def detect(file: UploadFile = File(...)) -> JSONResponse:  # noqa: B008 - FastAPI requires the File(...) default-marker idiom
        try:
            raw = await file.read()
            payload = service.detect_image(
                raw,
                filename=file.filename or "capture",
                media_type=file.content_type,
            )
        except service.DetectFailure as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        except Exception:
            log.exception("detect failed for upload %r", file.filename)
            return JSONResponse(status_code=500, content={"detail": _UNEXPECTED})
        return JSONResponse(status_code=200, content=payload)

    return app


app = create_app()
