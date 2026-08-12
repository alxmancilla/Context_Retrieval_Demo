import os

import pytest

from core.providers.rerank import create_voyage_reranker
from core.settings import get_settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.voyage_live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_INTEGRATION") != "1",
        reason="set RUN_LIVE_INTEGRATION=1 to run live integration tests",
    ),
]


def test_voyage_reranker_returns_aligned_scores():
    settings = get_settings()
    if not settings.voyage_api_key:
        pytest.skip("VOYAGE_API_KEY is not configured")
    reranker = create_voyage_reranker(
        api_key=settings.voyage_api_key,
        model=settings.voyage_rerank_model,
        timeout_seconds=settings.voyage_rerank_timeout_seconds,
        max_retries=settings.voyage_rerank_max_retries,
    )
    assert reranker is not None
    hits = [
        {"source": "github", "title": "Authentication", "content": "OAuth 2 with PKCE"},
        {"source": "teams", "title": "Caching", "content": "Redis cache expiration"},
    ]
    reranked = reranker.rerank("How does authentication work?", hits)
    assert len(reranked) == 2
    assert all(0.0 <= hit["rerank_score"] <= 1.0 for hit in reranked)
    assert reranked[0]["rerank_score"] > reranked[1]["rerank_score"]