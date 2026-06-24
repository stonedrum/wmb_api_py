from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def api_ok(data: Any = None, message: str = "") -> JSONResponse:
    return JSONResponse({"success": True, "message": message, "data": data})


def api_fail(message: str, data: Any = None, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"success": False, "message": message, "data": data}, status_code=status_code)
