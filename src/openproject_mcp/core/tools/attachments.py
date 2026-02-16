from __future__ import annotations

import base64
import io
import json
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openproject_mcp.core.client import (
    OpenProjectClient,
    OpenProjectClientError,
    OpenProjectHTTPError,
)
from openproject_mcp.core.hal import parse_id_from_href
from openproject_mcp.core.tools._collections import embedded_elements

MAX_PAGE_SIZE = 200
DEFAULT_PREVIEW_MAX_BYTES = 1024
DEFAULT_PAGE_SIZE = 50


def _clamp_page_size(page_size: int) -> int:
    return max(1, min(page_size, MAX_PAGE_SIZE))


def _parse_disposition_filename(content_disposition: Optional[str]) -> Optional[str]:
    if not content_disposition:
        return None
    parts = content_disposition.split(";")
    for part in parts:
        if "filename=" in part:
            val = part.split("=", 1)[1].strip().strip('"')
            return val or None
    return None


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
    page_size: int = DEFAULT_PAGE_SIZE,
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


async def _attachment_download_url(
    client: OpenProjectClient, attachment_id: int
) -> Tuple[str, Optional[str]]:
    payload = await client.get(
        f"/api/v3/attachments/{attachment_id}", tool="attachments"
    )
    links = payload.get("_links", {}) if isinstance(payload, dict) else {}
    download_href = None
    if isinstance(links, dict):
        download_href = links.get("downloadLocation", {}).get("href")
    if not download_href:
        raise OpenProjectClientError("Attachment downloadLocation missing.")
    file_name = payload.get("fileName") if isinstance(payload, dict) else None
    return download_href, file_name


async def download_attachment(
    client: OpenProjectClient,
    attachment_id: int,
    *,
    dest_path: Optional[str] = None,
    overwrite: bool = False,
) -> str:
    """
    Download attachment to disk (server-side filesystem).
    Returns the saved absolute path.
    """
    download_href, file_name = await _attachment_download_url(client, attachment_id)

    # Determine destination path
    dest = Path(dest_path) if dest_path else None
    if dest is None:
        dest = Path(".")
    if dest.is_dir():
        dest = dest / (file_name or f"attachment-{attachment_id}")
    if dest.exists() and not overwrite:
        raise OpenProjectClientError(f"File exists: {dest}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Stream download
    try:
        async with client.http.stream("GET", download_href) as resp:
            if resp.status_code < 200 or resp.status_code >= 300:
                raise await client._to_http_error(resp, method="GET")
            with dest.open("wb") as fh:
                async for chunk in resp.aiter_bytes():
                    fh.write(chunk)
    except OpenProjectHTTPError:
        # Cleanup partial file
        if dest.exists():
            dest.unlink(missing_ok=True)
        raise
    except Exception as exc:
        if dest.exists():
            dest.unlink(missing_ok=True)
        raise OpenProjectClientError(f"Failed to download attachment: {exc}") from exc

    return str(dest.resolve())


async def get_attachment_content(
    client: OpenProjectClient,
    attachment_id: int,
    *,
    max_bytes: int = DEFAULT_PREVIEW_MAX_BYTES,
) -> Dict[str, Any]:
    """
    Get a small preview of attachment bytes (base64) using Range request.
    """
    if max_bytes <= 0:
        raise ValueError("max_bytes must be > 0")

    download_href, _ = await _attachment_download_url(client, attachment_id)

    headers = {"Range": f"bytes=0-{max_bytes-1}"}
    content: Optional[bytes] = None
    content_type: Optional[str] = None

    try:
        resp = await client.http.get(download_href, headers=headers)
        if resp.status_code == 416:
            # Retry without range
            resp = await client.http.get(download_href)
        if resp.status_code < 200 or resp.status_code >= 300:
            raise await client._to_http_error(resp, method="GET")
        content_type = resp.headers.get("Content-Type")
        data = resp.content or b""
        content = data[:max_bytes]
    except OpenProjectHTTPError:
        raise
    except Exception as exc:
        raise OpenProjectClientError(
            f"Failed to fetch attachment content: {exc}"
        ) from exc

    return {
        "bytes": base64.b64encode(content or b"").decode("ascii"),
        "size": len(content or b""),
        "content_type": content_type,
    }
