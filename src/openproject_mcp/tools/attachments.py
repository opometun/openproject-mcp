from __future__ import annotations

import base64
import io
import json
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional

from openproject_mcp.client import (
    OpenProjectClient,
    OpenProjectClientError,
    OpenProjectHTTPError,
)
from openproject_mcp.hal import parse_id_from_href
from openproject_mcp.tools._collections import embedded_elements

MAX_PAGE_SIZE = 200


def _clamp_page_size(page_size: int) -> int:
    return max(1, min(page_size, MAX_PAGE_SIZE))


async def attach_file_to_wp(
    client: OpenProjectClient,
    wp_id: int,
    file_path: Optional[str] = None,
    *,
    description: Optional[str] = None,
    file_name: Optional[str] = None,
    content: Optional[bytes] = None,
    content_base64: Optional[str] = None,
    content_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Uploads a file as an attachment to a work package.
    Uses documented endpoint: POST /api/v3/work_packages/{id}/attachments
    Multipart parts (exact names):
    - metadata: application/json {"fileName": "...", "description": "..."}
    - file: binary content
    """
    if content is not None and content_base64 is not None:
        raise OpenProjectClientError(
            "Provide either content or content_base64, not both."
        )

    # Resolve file bytes and filename
    if content is None and content_base64 is not None:
        try:
            content = base64.b64decode(content_base64)
        except Exception as exc:
            raise OpenProjectClientError(f"Invalid base64 content: {exc}") from exc

    path = Path(file_path) if file_path else None
    if content is None:
        if path is None:
            raise OpenProjectClientError(
                "Either file_path or content/content_base64 must be provided."
            )
        if not path.is_file():
            raise OpenProjectClientError(f"File not found: {file_path}")
        fname = file_name or path.name
        ctype = (
            content_type or mimetypes.guess_type(fname)[0] or "application/octet-stream"
        )
        file_handle = path.open("rb")
        close_handle = True
    else:
        fname = file_name or (path.name if path else "attachment.bin")
        ctype = (
            content_type or mimetypes.guess_type(fname)[0] or "application/octet-stream"
        )
        file_handle = io.BytesIO(content)
        close_handle = False

    # Validate non-empty content
    pos = file_handle.tell()
    file_handle.seek(0, io.SEEK_END)
    size = file_handle.tell()
    file_handle.seek(pos)
    if size == 0:
        if close_handle:
            file_handle.close()
        raise OpenProjectClientError("Attachment content is empty; refusing to upload.")

    metadata = {"fileName": fname}
    if description:
        metadata["description"] = description

    # Manually build multipart to include metadata and file with exact part names
    try:
        files = {
            # filename None so it is treated as a form field, not a file
            "metadata": (None, json.dumps(metadata), "application/json"),
            "file": (fname, file_handle, ctype),
        }
        # Temporarily drop JSON content-type so httpx sets multipart boundary
        old_ct = client.http.headers.pop("Content-Type", None)
        try:
            resp = await client.http.post(
                f"/api/v3/work_packages/{wp_id}/attachments",
                files=files,
                headers={"Accept": client.http.headers.get("Accept")},
            )
        finally:
            if old_ct is not None:
                client.http.headers["Content-Type"] = old_ct
    except (OpenProjectClientError, OpenProjectHTTPError):
        raise
    except Exception as exc:
        raise OpenProjectClientError(f"Failed to upload attachment: {exc}") from exc
    finally:
        if close_handle:
            file_handle.close()

    if resp.status_code < 200 or resp.status_code >= 300:
        raise await client._to_http_error(resp, method="POST")

    return client._safe_json(resp)


async def list_attachments(
    client: OpenProjectClient,
    wp_id: int,
    *,
    offset: int = 0,
    page_size: int = 50,
) -> Dict[str, Any]:
    """
    List attachments for a work package.
    Note: 404 may indicate missing permissions or non-existent work package.
    """
    if offset < 0:
        raise ValueError("offset must be >= 0")
    page_size = _clamp_page_size(page_size)

    try:
        payload = await client.get(
            f"/api/v3/work_packages/{wp_id}/attachments",
            params={"offset": offset, "pageSize": page_size},
            tool="attachments",
        )
    except OpenProjectHTTPError:
        # Surface 404 as-is (could be missing perms)
        raise

    elements = embedded_elements(payload)
    items: List[Dict[str, Any]] = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        att_id = el.get("id") or parse_id_from_href(
            el.get("_links", {}).get("self", {}).get("href", "")
        )
        file_name = el.get("fileName") or el.get("_links", {}).get("self", {}).get(
            "title"
        )
        file_size = el.get("fileSize")
        download_href = (
            el.get("_links", {}).get("downloadLocation", {}).get("href")
            if isinstance(el.get("_links", {}), dict)
            else None
        )
        items.append(
            {
                "id": att_id,
                "file_name": file_name,
                "file_size": file_size,
                "download_href": download_href,
            }
        )

    total = payload.get("total") if isinstance(payload, dict) else None
    next_offset: Optional[int] = None
    if isinstance(total, int) and (offset + page_size) < total:
        next_offset = offset + page_size

    return {
        "items": items,
        "offset": offset,
        "page_size": page_size,
        "total": total if isinstance(total, int) else None,
        "next_offset": next_offset,
    }
