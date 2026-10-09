"""En-têtes de sécurité HTTP ajoutés à toutes les réponses (check-list sécurité MVola, site web).

Middleware ASGI pur (pas BaseHTTPMiddleware) : les réponses en streaming, comme les images
produit servies depuis MinIO, ne sont pas mises en mémoire.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# L'API ne renvoie que du JSON et des images : rien ne doit y être exécuté ni encadré.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
# Pages de documentation (Scalar / ReDoc, hors production) : scripts et styles depuis leurs CDN.
DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https://accounts.google.com https://oauth2.googleapis.com https://*.scalar.com; "
    "frame-ancestors 'none'; base-uri 'self'"
)
DOCS_PATHS = ("/docs", "/redoc")
HSTS = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        csp = DOCS_CSP if path.startswith(DOCS_PATHS) else API_CSP
        headers = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"strict-origin-when-cross-origin"),
            # Protection X-XSS dépréciée : désactivée explicitement, la CSP la remplace.
            (b"x-xss-protection", b"0"),
            (b"content-security-policy", csp.encode()),
        ]
        if self.hsts:
            # Uniquement derrière HTTPS (production) : HSTS sur http://localhost n'a pas de sens.
            headers.append((b"strict-transport-security", HSTS.encode()))

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing = {name.lower() for name, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [
                    (name, value) for name, value in headers if name not in existing
                ]
            await send(message)

        await self.app(scope, receive, send_with_headers)
