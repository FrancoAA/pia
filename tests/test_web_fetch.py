"""Tests for WebFetchTool."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.helpers import make_app
from pia.tools.web_fetch import (
    WebFetchTool,
    DEFAULT_TIMEOUT,
    MAX_CONTENT_SIZE,
    MAX_OUTPUT_LENGTH,
)


def _mock_response(
    *,
    status_code: int = 200,
    content: bytes = b"",
    text: str | None = None,
    content_type: str = "text/html",
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.text = text if text is not None else content.decode("utf-8", errors="replace")
    resp.headers = {"content-type": content_type}
    return resp


class TestWebFetchSchema(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = WebFetchTool(make_app())

    def test_schema_name_and_description(self) -> None:
        s = self.tool.schema()
        self.assertEqual(s.name, "web_fetch")
        self.assertIn("Fetch", s.description)

    def test_url_is_required(self) -> None:
        s = self.tool.schema()
        url_param = next(p for p in s.parameters if p.name == "url")
        self.assertTrue(url_param.required)

    def test_optional_params(self) -> None:
        s = self.tool.schema()
        for name in ("headers", "timeout", "raw"):
            param = next(p for p in s.parameters if p.name == name)
            self.assertFalse(param.required, f"{name} should be optional")


class TestWebFetchDryRun(unittest.TestCase):
    def test_dry_run_returns_early(self) -> None:
        tool = WebFetchTool(make_app(dry_run=True))
        result = tool.execute(url="https://example.com")
        self.assertIn("[dry-run]", result)
        self.assertIn("https://example.com", result)


class TestWebFetchValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = WebFetchTool(make_app())

    def test_invalid_scheme_ftp(self) -> None:
        result = self.tool.execute(url="ftp://example.com/file.txt")
        self.assertIn("Error", result)
        self.assertIn("http", result)

    def test_invalid_scheme_no_scheme(self) -> None:
        result = self.tool.execute(url="example.com")
        self.assertIn("Error", result)

    def test_invalid_headers_json(self) -> None:
        with patch("pia.tools.web_fetch.httpx") as mock_httpx:
            # Should fail before making request
            result = self.tool.execute(url="https://example.com", headers="not json")
            self.assertIn("Error", result)
            self.assertIn("invalid headers JSON", result)

    def test_headers_must_be_object(self) -> None:
        result = self.tool.execute(url="https://example.com", headers='["a","b"]')
        self.assertIn("Error", result)
        self.assertIn("JSON object", result)


class TestWebFetchHTTP(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = WebFetchTool(make_app())

    def _patch_client(self, response: MagicMock):
        """Return a patch context that makes httpx.Client().get() return *response*."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = response
        return patch("pia.tools.web_fetch.httpx.Client", return_value=mock_client)

    def test_http_error_status(self) -> None:
        resp = _mock_response(status_code=404, content=b"Not Found")
        with self._patch_client(resp):
            result = self.tool.execute(url="https://example.com/missing")
        self.assertIn("Error", result)
        self.assertIn("404", result)

    def test_timeout(self) -> None:
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.TimeoutException("timed out")
        with patch("pia.tools.web_fetch.httpx.Client", return_value=mock_client):
            result = self.tool.execute(url="https://example.com")
        self.assertIn("Error", result)
        self.assertIn("timed out", result)

    def test_request_error(self) -> None:
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.ConnectError("connection refused")
        with patch("pia.tools.web_fetch.httpx.Client", return_value=mock_client):
            result = self.tool.execute(url="https://example.com")
        self.assertIn("Error", result)
        self.assertIn("request failed", result)

    def test_content_too_large(self) -> None:
        big = b"x" * (MAX_CONTENT_SIZE + 1)
        resp = _mock_response(content=big, content_type="text/plain")
        with self._patch_client(resp):
            result = self.tool.execute(url="https://example.com/huge")
        self.assertIn("Error", result)
        self.assertIn("too large", result)

    def test_plain_text_fetch(self) -> None:
        resp = _mock_response(
            content=b"Hello, world!", content_type="text/plain"
        )
        with self._patch_client(resp):
            result = self.tool.execute(url="https://example.com/hello.txt")
        self.assertIn("Hello, world!", result)
        self.assertIn("text/plain", result)

    def test_json_fetch(self) -> None:
        body = b'{"key": "value"}'
        resp = _mock_response(content=body, content_type="application/json")
        with self._patch_client(resp):
            result = self.tool.execute(url="https://example.com/api")
        self.assertIn('"key"', result)
        self.assertIn("application/json", result)

    def test_output_truncation(self) -> None:
        big_text = "a" * (MAX_OUTPUT_LENGTH + 500)
        resp = _mock_response(
            content=big_text.encode(), content_type="text/plain"
        )
        with self._patch_client(resp):
            result = self.tool.execute(url="https://example.com/big.txt")
        self.assertIn("(output truncated)", result)

    def test_raw_mode_returns_text(self) -> None:
        html = b"<h1>Title</h1><p>Body</p>"
        resp = _mock_response(content=html, content_type="text/html")
        with self._patch_client(resp):
            result = self.tool.execute(url="https://example.com", raw=True)
        self.assertIn("<h1>Title</h1>", result)

    def test_raw_mode_binary_returns_metadata(self) -> None:
        resp = _mock_response(content=b"\x89PNG", content_type="image/png")
        with self._patch_client(resp):
            result = self.tool.execute(url="https://example.com/img.png", raw=True)
        self.assertIn("binary content", result)

    def test_custom_headers_passed(self) -> None:
        resp = _mock_response(content=b"ok", content_type="text/plain")
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = resp
        with patch("pia.tools.web_fetch.httpx.Client", return_value=mock_client):
            self.tool.execute(
                url="https://example.com",
                headers='{"Authorization": "Bearer tok123"}',
            )
        call_kwargs = mock_client.get.call_args
        headers_sent = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        self.assertIn("Authorization", headers_sent)
        self.assertEqual(headers_sent["Authorization"], "Bearer tok123")

    def test_metadata_header_present(self) -> None:
        resp = _mock_response(content=b"data", content_type="text/plain")
        with self._patch_client(resp):
            result = self.tool.execute(url="https://example.com/f.txt")
        self.assertIn("URL: https://example.com/f.txt", result)
        self.assertIn("Content-Type: text/plain", result)
        self.assertIn("Size: 4 bytes", result)


class TestWebFetchMarkitdown(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = WebFetchTool(make_app())

    def _patch_client(self, response: MagicMock):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = response
        return patch("pia.tools.web_fetch.httpx.Client", return_value=mock_client)

    @patch("pia.tools.web_fetch.HAS_MARKITDOWN", True)
    @patch("pia.tools.web_fetch.MarkItDown")
    def test_html_converted_with_markitdown(self, mock_md_cls: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.text_content = "# Converted Title\n\nSome paragraph."
        mock_md_cls.return_value.convert.return_value = mock_result

        html = b"<html><body><h1>Converted Title</h1><p>Some paragraph.</p></body></html>"
        resp = _mock_response(content=html, content_type="text/html; charset=utf-8")
        with self._patch_client(resp):
            result = self.tool.execute(url="https://example.com")
        self.assertIn("# Converted Title", result)
        self.assertIn("Some paragraph.", result)

    @patch("pia.tools.web_fetch.HAS_MARKITDOWN", True)
    @patch("pia.tools.web_fetch.MarkItDown")
    def test_markitdown_empty_output_falls_back(self, mock_md_cls: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.text_content = ""
        mock_md_cls.return_value.convert.return_value = mock_result

        html = b"<html><body>raw content</body></html>"
        resp = _mock_response(content=html, content_type="text/html")
        with self._patch_client(resp):
            result = self.tool.execute(url="https://example.com")
        # Should fall back to raw text since conversion was empty
        self.assertIn("raw content", result)

    @patch("pia.tools.web_fetch.HAS_MARKITDOWN", True)
    @patch("pia.tools.web_fetch.MarkItDown")
    def test_markitdown_exception_falls_back(self, mock_md_cls: MagicMock) -> None:
        mock_md_cls.return_value.convert.side_effect = RuntimeError("parse error")

        html = b"<html>fallback content</html>"
        resp = _mock_response(content=html, content_type="text/html")
        with self._patch_client(resp):
            result = self.tool.execute(url="https://example.com")
        self.assertIn("fallback content", result)

    @patch("pia.tools.web_fetch.HAS_MARKITDOWN", True)
    @patch("pia.tools.web_fetch.MarkItDown")
    def test_pdf_converted_with_markitdown(self, mock_md_cls: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.text_content = "PDF text content here."
        mock_md_cls.return_value.convert.return_value = mock_result

        resp = _mock_response(content=b"%PDF-1.4", content_type="application/pdf")
        with self._patch_client(resp):
            result = self.tool.execute(url="https://example.com/doc.pdf")
        self.assertIn("PDF text content here.", result)

    @patch("pia.tools.web_fetch.HAS_MARKITDOWN", False)
    def test_no_markitdown_returns_raw_html(self) -> None:
        html = b"<h1>Raw HTML</h1>"
        resp = _mock_response(content=html, content_type="text/html")
        with self._patch_client(resp):
            result = self.tool.execute(url="https://example.com")
        self.assertIn("<h1>Raw HTML</h1>", result)

    @patch("pia.tools.web_fetch.HAS_MARKITDOWN", False)
    def test_no_markitdown_binary_returns_metadata(self) -> None:
        resp = _mock_response(content=b"\x89PNG", content_type="image/png")
        with self._patch_client(resp):
            result = self.tool.execute(url="https://example.com/img.png")
        self.assertIn("binary content", result)
        self.assertIn("install markitdown", result)

    @patch("pia.tools.web_fetch.HAS_MARKITDOWN", True)
    @patch("pia.tools.web_fetch.MarkItDown")
    def test_markitdown_binary_failure_returns_message(self, mock_md_cls: MagicMock) -> None:
        mock_md_cls.return_value.convert.side_effect = RuntimeError("unsupported")

        resp = _mock_response(content=b"\x00\x01", content_type="application/octet-stream")
        with self._patch_client(resp):
            result = self.tool.execute(url="https://example.com/data.bin")
        self.assertIn("conversion failed", result)


if __name__ == "__main__":
    unittest.main()
