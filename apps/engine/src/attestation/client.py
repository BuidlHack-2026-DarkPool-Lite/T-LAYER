"""NEAR AI Cloud + NVIDIA attestation API 클라이언트."""

import logging

import httpx

from src.config import NEARAI_CLOUD_API_KEY, NEARAI_CLOUD_BASE_URL, NVIDIA_ATTESTATION_URL

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SEC = 10.0


async def fetch_attestation_report(model: str) -> dict | None:
    """NEAR AI Cloud에서 모델의 attestation report를 조회한다."""
    if not NEARAI_CLOUD_API_KEY:
        logger.error("NEARAI_CLOUD_API_KEY가 설정되지 않음")
        return None

    url = f"{NEARAI_CLOUD_BASE_URL}/v1/attestation/report"
    headers = {
        "Authorization": f"Bearer {NEARAI_CLOUD_API_KEY}",
        "Content-Type": "application/json",
    }
    params = {"model": model}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SEC) as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception:
        logger.exception("attestation report 조회 실패: model=%s", model)
        return None


async def verify_gpu_attestation(nvidia_payload: str) -> dict | None:
    """NVIDIA attestation 서비스로 GPU attestation을 검증한다."""
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SEC) as client:
            resp = await client.post(
                NVIDIA_ATTESTATION_URL,
                headers={
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                content=nvidia_payload,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        logger.exception("NVIDIA GPU attestation 검증 실패")
        return None
