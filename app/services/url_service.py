"""
WeCare — URL & Asset Path Resolution Service

Mirrors helpers/url and helpers/caretaker_documents caretaker_document_view_url.
"""

import re
from typing import Optional
from urllib.parse import urlparse
from app.core.config import get_settings


def public_file_path(path: Optional[str]) -> Optional[str]:
    """
    Route: public_file_path($path) — helpers/url L5-52
    Cleans and validates a path to ensure it safely references /uploads/...
    """
    if path is None:
        return None
    path_str = str(path).strip()
    if path_str == "":
        return None

    path_str = path_str.replace("\\", "/")
    try:
        parsed = urlparse(path_str)
        if parsed.path:
            path_str = parsed.path
    except Exception:
        pass

    path_str = re.sub(r"[?#].*$", "", path_str)
    path_str = re.sub(r"/+", "/", path_str)
    if re.search(r"(^|/)\.\.(/|$)", path_str):
        return None

    upload_pos = path_str.lower().find("/uploads/")
    if upload_pos == -1 and path_str.lower().startswith("uploads/"):
        upload_pos = 0

    if upload_pos == -1:
        return None

    clean = "/" + path_str[upload_pos:].lstrip("/")
    segments = []
    for segment in clean.split("/"):
        if segment == "" or segment == ".":
            continue
        if segment == "..":
            return None
        segments.append(segment)

    if not segments or segments[0].lower() != "uploads":
        return None

    return "/" + "/".join(segments)


def public_file_url(path: Optional[str]) -> Optional[str]:
    """
    Route: public_file_url($path) — helpers/url L54-63
    Resolves relative path to fully qualified URL.
    """
    clean_path = public_file_path(path)
    if clean_path is None:
        return None

    settings = get_settings()
    base_url = str(settings.APP_URL).rstrip("/")
    return f"{base_url}{clean_path}"


def caretaker_document_view_url(document_id: int) -> str:
    """
    Route: caretaker_document_view_url($documentId) — helpers/caretaker_documents L62-66
    """
    settings = get_settings()
    api_base = f"{str(settings.APP_URL).rstrip('/')}/api/v1"
    return f"{api_base}/caretaker/document_view?id={document_id}"
