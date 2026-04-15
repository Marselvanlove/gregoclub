import logging
import os

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def _filter_request_headers(headers: Request) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
    }


def _filter_response_headers(headers: httpx.Headers) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }


def create_dashboard_proxy_endpoint() -> APIRouter:
    upstream = os.getenv("DASHBOARD_UPSTREAM_URL", "http://dashboard:3000").rstrip("/")

    async def _proxy_to_dashboard(request: Request, path: str = "") -> Response:
        upstream_path = request.url.path
        if path == "" and not upstream_path.endswith("/dashboard"):
            upstream_path = "/dashboard"

        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
                upstream_response = await client.request(
                    request.method,
                    f"{upstream}{upstream_path}",
                    headers=_filter_request_headers(request),
                    params=request.query_params,
                    content=await request.body(),
                )
        except httpx.HTTPError as exc:
            logger.exception("Dashboard proxy error: %s", exc)
            raise HTTPException(status_code=502, detail="Dashboard upstream is unavailable") from exc

        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=_filter_response_headers(upstream_response.headers),
            media_type=upstream_response.headers.get("content-type"),
        )

    router.add_api_route("/dashboard", _proxy_to_dashboard, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
    router.add_api_route("/dashboard/{path:path}", _proxy_to_dashboard, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])

    return router
