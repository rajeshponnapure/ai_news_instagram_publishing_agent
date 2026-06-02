from __future__ import annotations

import http.client
import re
import ssl
import urllib.error
import urllib.request


# urllib/http.client reject any URL char outside printable ASCII: raw control
# chars and spaces raise http.client.InvalidURL (a bare HTTPException — NOT a
# URLError/OSError, so callers' `except URLError` miss it and the run aborts),
# and non-ASCII chars raise UnicodeEncodeError. Tracking beacons in scraped pages
# routinely carry both, e.g. "...&ec=Quality Visit – 30s+..." (space + en-dash).
_ILLEGAL_URL_CHARS = re.compile(r"[^\x21-\x7e]")


def _sanitize_url(url: str) -> str:
    """Percent-encode every non-printable-ASCII character (spaces, control chars,
    Unicode punctuation) so the URL is requestable. Already-encoded %XX is left
    intact since '%' is printable ASCII."""
    def _encode(match: re.Match) -> str:
        return "".join("%%%02X" % byte for byte in match.group(0).encode("utf-8"))

    return _ILLEGAL_URL_CHARS.sub(_encode, url)


def urlopen_with_cert_fallback(
    request: urllib.request.Request | str,
    timeout: float,
):
    """Open public article/media URLs, retrying only certificate-chain failures.

    Sanitizes illegal URL characters up front and normalizes the otherwise
    uncatchable http.client.InvalidURL/HTTPException into urllib.error.URLError
    so every caller's existing `except URLError` handling covers it.
    """
    if isinstance(request, urllib.request.Request):
        if _ILLEGAL_URL_CHARS.search(request.full_url):
            request.full_url = _sanitize_url(request.full_url)
    elif isinstance(request, str) and _ILLEGAL_URL_CHARS.search(request):
        request = _sanitize_url(request)

    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except http.client.HTTPException as exc:
        raise urllib.error.URLError(exc) from exc
    except urllib.error.URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        context = ssl._create_unverified_context()
        try:
            return urllib.request.urlopen(request, timeout=timeout, context=context)
        except http.client.HTTPException as exc2:
            raise urllib.error.URLError(exc2) from exc2
