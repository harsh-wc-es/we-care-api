"""
WeCare — API Exception Infrastructure (STEP 4)

Custom exception that produces the response envelope.
Registered as a FastAPI exception handler in main.py.
"""

from typing import Any, Optional

from fastapi import Request
from fastapi.responses import JSONResponse


class APIException(Exception):
    """
    Raise this anywhere to produce the standard error envelope.

    Usage:
        raise APIException("Invalid credentials", status_code=401)
        raise APIException("Validation failed", errors={"email": ["Required"]}, status_code=400)
    """

    def __init__(
        self,
        message: str = "An error occurred",
        errors: Any = None,
        status_code: int = 400,
    ):
        self.message = message
        self.errors = errors
        self.status_code = status_code
        super().__init__(message)


async def api_exception_handler(request: Request, exc: APIException) -> JSONResponse:
    """FastAPI exception handler for APIException."""
    errors = exc.errors
    if errors is not None and not isinstance(errors, (dict, list)):
        errors = {"general": [str(errors)]}

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.message,
            "data": None,
            "errors": errors,
        },
    )
