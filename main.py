import os

import uvicorn
from loguru import logger

from app.config import config


def _with_scheme(url_or_domain: str) -> str:
    value = url_or_domain.strip().rstrip("/")
    if not value:
        return ""
    if "://" in value:
        return value
    return f"https://{value}"


def get_docs_url() -> str:
    public_base_url = _with_scheme(
        os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or os.getenv("MPT_PUBLIC_BASE_URL")
        or os.getenv("MPT_ENDPOINT")
        or os.getenv("MPT_APP_ENDPOINT")
        or ""
    )
    if public_base_url:
        return f"{public_base_url}/docs"
    return f"http://127.0.0.1:{config.listen_port}/docs"


if __name__ == "__main__":
    logger.info(
        f"start server, bind: {config.listen_host}:{config.listen_port}, "
        f"docs: {get_docs_url()}"
    )
    uvicorn.run(
        app="app.asgi:app",
        host=config.listen_host,
        port=config.listen_port,
        reload=config.reload_debug,
        log_level="warning",
    )
