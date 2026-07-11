PUBLIC_ASSISTANT_NAME = "KKManus"
DEFAULT_ADK_APP_NAME = "kkmanus"

_LEGACY_ADK_APP_NAMES = {
    "fufanmanus",
}


def _normalize_text(value: str | None) -> str:
    return (value or "").strip()


def normalize_adk_app_name(app_name: str | None) -> str:
    normalized = _normalize_text(app_name)
    if not normalized:
        return DEFAULT_ADK_APP_NAME

    if normalized.lower() in _LEGACY_ADK_APP_NAMES:
        return DEFAULT_ADK_APP_NAME

    if normalized.lower() == PUBLIC_ASSISTANT_NAME.lower():
        return DEFAULT_ADK_APP_NAME

    return normalized


def normalize_event_author(author: str | None) -> str:
    normalized = _normalize_text(author)
    if not normalized:
        return "assistant"

    lowered = normalized.lower()
    if lowered == "user":
        return "user"

    if lowered == "assistant" or lowered == DEFAULT_ADK_APP_NAME or lowered in _LEGACY_ADK_APP_NAMES:
        return "assistant"

    return normalized
