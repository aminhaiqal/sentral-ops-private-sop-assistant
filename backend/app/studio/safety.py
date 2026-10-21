import html
import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class StudioError(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        self.code, self.message, self.retryable = code, message, retryable
        super().__init__(message)


def public_url(value: str) -> str:
    """Validate links only. Result URLs are never fetched by the server."""
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").encode("idna").decode().lower().rstrip(".")
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port not in {None, 443}
            or len(value) > 2000
            or any(ord(char) < 33 for char in value)
            or "\\" in value
        ):
            raise ValueError()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError()
        labels = host.split(".")
        if (
            len(labels) < 2
            or labels[-1] in {"localhost", "local", "internal", "test", "invalid", "onion"}
            or not re.fullmatch(r"[a-z]{2,63}", labels[-1])
            or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels
            )
        ):
            raise ValueError()
        query = []
        for key, item in parse_qsl(parsed.query, keep_blank_values=True):
            if SENSITIVE_KEY.search(key):
                raise ValueError()
            if not key.lower().startswith("utm_") and key.lower() not in {"gclid", "fbclid"}:
                query.append((key, item))
        return urlunsplit(("https", host, parsed.path or "/", urlencode(query), ""))
    except (ValueError, UnicodeError) as exc:
        raise StudioError(
            "unsafe_url", "The search provider returned an unsupported source URL."
        ) from exc


def company_domain(url: str) -> str:
    # One lead per host, including www variants. No guessed registrable-domain parsing.
    return (urlsplit(public_url(url)).hostname or "").removeprefix("www.")


def plain_text(value: str, limit: int) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", value)).split())[:limit]


def normalized(value: str) -> str:
    return re.sub(r"[^\w]", "", value.casefold())


SENSITIVE_KEY = re.compile(
    r"(?i)(?:password|secret|api.?key|authorization|access.?token|credential)"
)
SENSITIVE_TEXT = re.compile(
    r"(?i)\b(?:bearer\s+[a-z0-9._~-]+|(?:sk|pk)_(?:live|test)_[a-z0-9]+|sk-[a-z0-9_-]{12,}|"
    r"(?:api[_ -]?key|password|secret|access[_ -]?token)\s*[:=]\s*[^\s,;]+)"
)


def redact(value):
    """Defense in depth for stored/displayed user input, provider content and logs."""
    if isinstance(value, dict):
        return {
            key: "[redacted]" if SENSITIVE_KEY.search(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return SENSITIVE_TEXT.sub("[redacted]", value)
    return value
