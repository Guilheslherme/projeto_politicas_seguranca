"""Cabeçalhos de segurança que dependem do nonce de cada resposta."""

import secrets


class ContentSecurityPolicyMiddleware:
    """Gera um nonce por requisição e limita o carregamento de recursos."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        nonce = secrets.token_urlsafe(18)
        request.csp_nonce = nonce

        response = self.get_response(request)
        response["Content-Security-Policy"] = "; ".join(
            (
                "default-src 'self'",
                f"script-src 'self' 'nonce-{nonce}'",
                "script-src-attr 'none'",
                "style-src 'self'",
                "img-src 'self' data:",
                "font-src 'self'",
                "connect-src 'self'",
                "object-src 'none'",
                "base-uri 'self'",
                "frame-ancestors 'none'",
                "form-action 'self'",
            )
        )
        return response
