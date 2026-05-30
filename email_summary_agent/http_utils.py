from __future__ import annotations

import ssl
import urllib.error
import urllib.request


def urlopen_with_cert_fallback(
    request: urllib.request.Request | str,
    timeout: float,
):
    """Open public article/media URLs, retrying only certificate-chain failures."""
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        context = ssl._create_unverified_context()
        return urllib.request.urlopen(request, timeout=timeout, context=context)
