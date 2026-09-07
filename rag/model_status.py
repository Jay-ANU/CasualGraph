"""Public, secret-free model configuration status (not a connectivity probe)."""
from configs import settings


def get_model_status() -> dict:
    configured = settings.openai_configured()
    deep_configured = configured if settings.LLM_PROVIDER == "deepseek" else settings.anthropic_configured()
    return {
        "provider": settings.LLM_PROVIDER,
        "model": settings.OPENAI_MODEL,
        "configured": configured,
        "connectivity_verified": False,
        "modes": {
            "flash": {"model": settings.OPENAI_MODEL, "configured": configured, "thinking": False},
            "deep": {"model": settings.RAG_DEEP_MODEL, "configured": deep_configured, "thinking": settings.LLM_PROVIDER == "deepseek"},
        },
        "extraction": {"model": settings.DEEPSEEK_EXTRACTION_MODEL, "configured": settings.deepseek_configured()},
        "vision": {"model": settings.VISION_MODEL or None, "configured": bool(settings.VISION_API_KEY and settings.VISION_BASE_URL and settings.VISION_MODEL)},
    }
