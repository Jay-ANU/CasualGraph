"""Client for the standalone ESG QLoRA extraction API."""

from __future__ import annotations

from typing import Dict

import requests

from config import Config


class ESGModelClient:
    """Call the local AI extraction service and return normalized JSON."""

    def __init__(self) -> None:
        self.base_url = Config.AI_SERVICE_URL.rstrip("/")
        self.timeout = Config.AI_SERVICE_TIMEOUT

    def is_enabled(self) -> bool:
        return Config.PREFER_LOCAL_AI_EXTRACTION

    def extract(self, text: str) -> Dict:
        response = requests.post(
            f"{self.base_url}/extract",
            json={"text": text},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("AI service returned non-object JSON")
        return payload


esg_model_client = ESGModelClient()
