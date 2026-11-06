import os

from llama_cloud import APIError, APITimeoutError, LlamaCloud, PollingError, PollingTimeoutError

from app.core.limits import timeout

TIERS = frozenset({"fast", "cost_effective", "agentic", "agentic_plus"})
ParseError = (APIError, PollingError, PollingTimeoutError, ValueError)


def api_key() -> str:
    return os.getenv("LLAMA_CLOUD_API_KEY", "").strip()


def enabled() -> bool:
    return bool(api_key())


def tier() -> str:
    value = os.getenv("LLAMA_PARSE_TIER", "").strip()
    return value if value in TIERS else "cost_effective"


def parse_file(filename: str, data: bytes) -> list[tuple[int, str]]:
    client = LlamaCloud(api_key=api_key(), timeout=timeout("PARSE_REQUEST_TIMEOUT_SECONDS"), max_retries=2)
    result = client.parsing.parse(
        tier=tier(),
        version="latest",
        upload_file=(filename, data),
        expand=["markdown"],
        timeout=timeout("PARSE_TIMEOUT_SECONDS"),
    )
    pages = result.markdown.pages if result.markdown else []
    return [(page.page_number, page.markdown.strip()) for page in pages if page.success and page.markdown.strip()]
