from __future__ import annotations

import json
import os
import tempfile
from pathlib import PurePosixPath
from typing import Any, TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from pia.tools._base import ToolSchema, ToolParam

if TYPE_CHECKING:
    from pia.app import App

try:
    from markitdown import MarkItDown

    HAS_MARKITDOWN = True
except ImportError:  # pragma: no cover
    HAS_MARKITDOWN = False

DEFAULT_TIMEOUT = 30
MAX_CONTENT_SIZE = 512 * 1024  # 512 KB
MAX_OUTPUT_LENGTH = 100_000  # characters
USER_AGENT = "pia-agent/0.1 (httpx)"

# Map common MIME types to file suffixes for markitdown temp files.
SUFFIX_MAP: dict[str, str] = {
    "text/html": ".html",
    "application/pdf": ".pdf",
    "application/json": ".json",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}

# MIME prefixes that are plain text and can be returned raw.
_TEXT_PREFIXES = ("text/", "application/json", "application/xml", "application/javascript")


def _is_text_type(mime: str) -> bool:
    return any(mime.startswith(p) for p in _TEXT_PREFIXES)


def _suffix_for(mime: str, url: str) -> str:
    """Return a file suffix suitable for *mime*, falling back to the URL path."""
    suffix = SUFFIX_MAP.get(mime)
    if suffix:
        return suffix
    path_suffix = PurePosixPath(urlparse(url).path).suffix
    if path_suffix:
        return path_suffix
    return ".bin"


class WebFetchTool:
    name = "web_fetch"
    description = (
        "Fetch a URL and return its contents. "
        "Web pages and supported documents (PDF, DOCX, images …) are "
        "automatically converted to Markdown for easy reading."
    )

    def __init__(self, app: App) -> None:
        self.app = app

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParam(
                    name="url",
                    type="string",
                    description="The URL to fetch (must start with http:// or https://).",
                    required=True,
                ),
                ToolParam(
                    name="headers",
                    type="string",
                    description='Optional JSON string of extra HTTP headers, e.g. \'{"Authorization": "Bearer …"}\'.',
                    required=False,
                ),
                ToolParam(
                    name="timeout",
                    type="integer",
                    description=f"Request timeout in seconds. Default {DEFAULT_TIMEOUT}.",
                    required=False,
                ),
                ToolParam(
                    name="raw",
                    type="boolean",
                    description="If true, skip Markdown conversion and return raw content.",
                    required=False,
                ),
            ],
        )

    # ------------------------------------------------------------------
    # execute
    # ------------------------------------------------------------------

    def execute(self, **kwargs: Any) -> str:
        url: str = kwargs["url"]
        raw: bool = kwargs.get("raw", False)
        timeout: int = kwargs.get("timeout", DEFAULT_TIMEOUT)
        extra_headers: str | None = kwargs.get("headers")

        # Dry-run guard
        if self.app.config.dry_run:
            return f"[dry-run] Would fetch: {url}"

        # URL validation
        if not url.startswith(("http://", "https://")):
            return "Error: URL must start with http:// or https://"

        # Parse optional headers
        merged_headers: dict[str, str] = {"User-Agent": USER_AGENT}
        if extra_headers:
            try:
                parsed = json.loads(extra_headers)
                if not isinstance(parsed, dict):
                    return "Error: headers must be a JSON object."
                merged_headers.update(parsed)
            except json.JSONDecodeError as e:
                return f"Error: invalid headers JSON: {e}"

        # Fetch
        try:
            with httpx.Client(follow_redirects=True, timeout=timeout) as client:
                response = client.get(url, headers=merged_headers)
        except httpx.TimeoutException:
            return f"Error: request timed out after {timeout} seconds."
        except httpx.RequestError as e:
            return f"Error: request failed: {e}"

        # Status check
        if response.status_code >= 400:
            return f"Error: HTTP {response.status_code} for {url}"

        # Size check
        size = len(response.content)
        if size > MAX_CONTENT_SIZE:
            return (
                f"Error: response too large ({size} bytes). "
                f"Max allowed: {MAX_CONTENT_SIZE} bytes."
            )

        # Determine MIME type
        content_type = response.headers.get("content-type", "")
        mime = content_type.split(";")[0].strip().lower()

        # Convert / return content
        body = self._convert(response, mime, url, raw)

        # Truncate if needed
        if len(body) > MAX_OUTPUT_LENGTH:
            body = body[:MAX_OUTPUT_LENGTH] + "\n\n(output truncated)"

        header = f"URL: {url}\nContent-Type: {mime}\nSize: {size} bytes\n\n"
        return header + body

    # ------------------------------------------------------------------
    # conversion helpers
    # ------------------------------------------------------------------

    def _convert(self, response: httpx.Response, mime: str, url: str, raw: bool) -> str:
        """Return a text representation of *response*, converting when possible."""
        if raw:
            if _is_text_type(mime):
                return response.text
            return f"(binary content, {len(response.content)} bytes)"

        if HAS_MARKITDOWN:
            return self._convert_with_markitdown(response, mime, url)

        # Fallback: no markitdown installed
        if _is_text_type(mime):
            return response.text
        return f"(binary content, {len(response.content)} bytes — install markitdown for conversion)"

    def _convert_with_markitdown(
        self, response: httpx.Response, mime: str, url: str
    ) -> str:
        suffix = _suffix_for(mime, url)
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        try:
            os.write(fd, response.content)
            os.close(fd)
            md = MarkItDown()
            result = md.convert(tmp_path)
            text = result.text_content
            if text and text.strip():
                return text
            # Conversion produced nothing useful — fallback
            if _is_text_type(mime):
                return response.text
            return f"(markitdown returned empty output for {mime})"
        except Exception as e:
            # markitdown failed — graceful fallback
            if _is_text_type(mime):
                return response.text
            return f"(markitdown conversion failed: {e})"
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
