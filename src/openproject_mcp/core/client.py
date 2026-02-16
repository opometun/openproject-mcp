import asyncio
import logging
import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Type, TypeVar

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from . import hal

T = TypeVar("T", bound=BaseModel)


class OpenProjectClientError(Exception):
    """Base error for client failures."""


class OpenProjectHTTPError(OpenProjectClientError):
    def __init__(
        self,
        *,
        status_code: int,
        method: str,
        url: str,
        message: str,
        response_json: Optional[Dict[str, Any]] = None,
        response_text: Optional[str] = None,
    ):
        super().__init__(f"{status_code} {method} {url}: {message}")
        self.status_code = status_code
        self.method = method
        self.url = url
        self.response_json = response_json
        self.response_text = response_text


@dataclass(frozen=True)
class RetryConfig:
    max_retries: int = 2  # total extra attempts
    backoff_base_seconds: float = 0.3  # 0.3, 0.6, 1.2...
    retry_statuses: frozenset[int] = frozenset({502, 503, 504})
    retry_on_429: bool = False


class OpenProjectParseError(OpenProjectClientError):
    pass


class OpenProjectModelValidationError(OpenProjectClientError):
    pass


class OpenProjectClient:
    """
    Shared HTTP client for OpenProject HAL+JSON API.
    - Handles auth, base URL, timeouts, retries
    - Returns raw dict payloads or optional Pydantic-validated models
    - No business logic; tools own domain decisions
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 10.0,
        retry: Optional[RetryConfig] = None,
        logger: Optional[logging.Logger] = None,
        http: Optional[httpx.AsyncClient] = None,
    ):
        base_url = (base_url or "").rstrip("/")
        api_key = api_key or ""

        if not base_url:
            raise ValueError("base_url must be provided.")
        if not api_key:
            raise ValueError("api_key must be provided.")

        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.retry = retry if retry is not None else RetryConfig()
        self.log = logger or logging.getLogger("openproject_mcp.client")

        # Prefer httpx basic auth rather than manual base64 encoding
        auth = httpx.BasicAuth("apikey", api_key)

        self._owns_http = http is None
        self.http = http or httpx.AsyncClient(
            base_url=self.base_url,
            auth=auth,
            headers={
                "Accept": "application/hal+json",
                "Content-Type": "application/json",
            },
            timeout=timeout_seconds,
        )

    @classmethod
    def from_env(cls, **kwargs) -> "OpenProjectClient":
        load_dotenv()
        base_url = os.getenv("OPENPROJECT_BASE_URL", "").strip()
        api_key = os.getenv("OPENPROJECT_API_KEY", "").strip()
        return cls(base_url=base_url, api_key=api_key, **kwargs)

    async def aclose(self) -> None:
        if self._owns_http:
            await self.http.aclose()

    async def __aenter__(self) -> "OpenProjectClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        tool: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Core request method.
        - Retries on transient failures (network/timeouts + 502/503/504; optionally 429)
        - Raises OpenProjectHTTPError on non-2xx HTTP responses
        - Raises OpenProjectClientError on network/timeout errors after retries
        - Raises OpenProjectParseError if response isn't valid JSON
        - Returns parsed JSON dict on success
        """
        method = method.upper()
        start = time.perf_counter()

        # url can be relative ("/api/v3/...") or absolute.
        req_url = url

        attempt = 0

        while True:
            try:
                resp = await self.http.request(
                    method, req_url, params=params, json=json
                )
                duration_ms = int((time.perf_counter() - start) * 1000)

                # structured-ish log without secrets
                self.log.debug(
                    "op.request",
                    extra={
                        "tool": tool,
                        "method": method,
                        "url": str(resp.request.url),
                        "status": resp.status_code,
                        "duration_ms": duration_ms,
                        "attempt": attempt,
                    },
                )

                # Retry certain status codes
                if resp.status_code in self.retry.retry_statuses or (
                    self.retry.retry_on_429 and resp.status_code == 429
                ):
                    if attempt < self.retry.max_retries:
                        await asyncio.sleep(
                            self.retry.backoff_base_seconds * (2**attempt)
                        )
                        attempt += 1
                        continue

                # Raise on non-2xx
                if resp.status_code < 200 or resp.status_code >= 300:
                    raise await self._to_http_error(resp, method=method)

                return self._safe_json(resp)

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
                if attempt < self.retry.max_retries:
                    await asyncio.sleep(self.retry.backoff_base_seconds * (2**attempt))
                    attempt += 1
                    continue
                raise OpenProjectClientError(
                    f"Network/timeout error calling {method} {url}: {exc}"
                ) from exc

            except httpx.HTTPError as exc:
                # Other httpx exceptions (rare) - do not blindly retry
                raise OpenProjectClientError(
                    f"HTTPX error calling {method} {url}: {exc}"
                ) from exc

    def _safe_json(self, resp: httpx.Response) -> Dict[str, Any]:
        # Handle empty responses (204 No Content, etc.)
        if not resp.content:
            return {}

        try:
            data = resp.json()
        except Exception as exc:
            snippet = (resp.text or "")[:500]
            raise OpenProjectParseError(
                f"Expected JSON from {resp.request.method} "
                f"{resp.request.url}, got non-JSON body snippet: "
                f"{snippet!r}"
            ) from exc

        if not isinstance(data, dict):
            raise OpenProjectParseError(
                f"Expected top-level JSON object from "
                f"{resp.request.method} {resp.request.url}, "
                f"got {type(data).__name__}"
            )
        return data

    async def _to_http_error(
        self, resp: httpx.Response, *, method: str
    ) -> OpenProjectHTTPError:
        url = str(resp.request.url)
        # Try JSON first; fall back to text snippet.
        response_json: Optional[Dict[str, Any]] = None
        response_text: Optional[str] = None
        message = "request failed"

        try:
            parsed = resp.json()
            if isinstance(parsed, dict):
                response_json = parsed
                # OpenProject errors often contain a "message" or embedded error details
                message = parsed.get("message") or parsed.get("error") or message
        except Exception:
            response_text = (resp.text or "")[:500]

        return OpenProjectHTTPError(
            status_code=resp.status_code,
            method=method,
            url=url,
            message=message,
            response_json=response_json,
            response_text=response_text,
        )

    async def get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        tool: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self.request("GET", url, params=params, tool=tool)

    async def post(
        self, url: str, *, json: Dict[str, Any], tool: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.request("POST", url, json=json, tool=tool)

    async def patch(
        self, url: str, *, json: Dict[str, Any], tool: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self.request("PATCH", url, json=json, tool=tool)

    async def post_file(
        self,
        url: str,
        *,
        file_path: str,
        field_name: str = "file",
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        tool: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload a file using multipart/form-data.
        - Streams from disk (does not load entire file into memory).
        - Returns parsed JSON if present; {} on empty body.
        - Retries are NOT applied to avoid duplicate uploads.
        """
        path = Path(file_path)
        if not path.is_file():
            raise OpenProjectClientError(f"File not found: {file_path}")

        filename = filename or path.name
        ctype = (
            content_type
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )

        start = time.perf_counter()
        try:
            with path.open("rb") as fh:
                # Temporarily drop default Content-Type so httpx can set multipart boundary.  # noqa: E501
                old_ct = self.http.headers.pop("Content-Type", None)
                try:
                    headers = {"Accept": self.http.headers.get("Accept")}
                    resp = await self.http.post(
                        url,
                        params=params,
                        files={field_name: (filename, fh, ctype)},
                        headers=headers,
                    )
                finally:
                    if old_ct is not None:
                        self.http.headers["Content-Type"] = old_ct
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
            raise OpenProjectClientError(
                f"Network/timeout error calling POST {url}: {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            raise OpenProjectClientError(
                f"HTTPX error calling POST {url}: {exc}"
            ) from exc

        duration_ms = int((time.perf_counter() - start) * 1000)
        self.log.debug(
            "op.upload",
            extra={
                "tool": tool,
                "method": "POST",
                "url": str(resp.request.url),
                "status": resp.status_code,
                "duration_ms": duration_ms,
            },
        )

        if resp.status_code < 200 or resp.status_code >= 300:
            raise await self._to_http_error(resp, method="POST")

        return self._safe_json(resp)

    async def request_model(
        self, model: Type[T], method: str, url: str, **kwargs: Any
    ) -> T:
        payload = await self.request(method, url, **kwargs)
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise OpenProjectModelValidationError(
                f"Response did not match model {model.__name__}: {exc}"
            ) from exc

    @staticmethod
    def link_href(payload: Dict[str, Any], rel: str) -> Optional[str]:
        return hal.get_link_href(payload, rel)

    @staticmethod
    def link_title(payload: Dict[str, Any], rel: str) -> Optional[str]:
        return hal.get_link_title(payload, rel)

    @staticmethod
    def embedded(payload: Dict[str, Any], rel: str) -> Optional[Dict[str, Any]]:
        return hal.get_embedded(payload, rel)
