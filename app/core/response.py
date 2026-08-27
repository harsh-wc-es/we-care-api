"""
WeCare — API Response Helpers (STEP 4)

Mirrors helpers/response response_json() envelope.

contract:
    {"success": bool, "message": str, "data": any|null, "errors": any|null}
"""

from decimal import Decimal
from typing import Any, Optional

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def success_response(
    message: str,
    data: Any = None,
    status_code: int = 200,
) -> JSONResponse:
    """
    response_json(true, $message, $data, null, $status_code)
    """
    content = {
        "success": True,
        "message": message,
        "data": data,
        "errors": None,
    }
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(content, custom_encoder={Decimal: float}),
    )


def error_response(
    message: str,
    errors: Any = None,
    status_code: int = 400,
) -> JSONResponse:
    """
    response_json(false, $message, null, $errors, $status_code)

    If errors is a plain string (not dict/list), wraps it as:
        {"general": [str]}
    matching response L36-38.
    """
    if errors is not None and not isinstance(errors, (dict, list)):
        errors = {"general": [str(errors)]}

    content = {
        "success": False,
        "message": message,
        "data": None,
        "errors": errors,
    }
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(content, custom_encoder={Decimal: float}),
    )
