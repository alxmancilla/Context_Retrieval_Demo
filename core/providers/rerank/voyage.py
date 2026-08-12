from math import isfinite

from voyageai import Client


class VoyageReranker:
    """Cross-encoder semantic reranking with aligned scores for every candidate."""

    def __init__(
        self, *, api_key: str, model: str = "rerank-2.5",
        timeout_seconds: float = 15.0, max_retries: int = 2,
    ) -> None:
        self.model = model
        self.client = Client(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    @staticmethod
    def _document(hit: dict) -> str:
        return (
            f"Source: {hit['source']}\n"
            f"Title: {hit['title']}\n"
            f"Content: {hit['content']}"
        )

    def rerank(self, query: str, hits: list[dict]) -> list[dict]:
        if not hits:
            return []
        response = self.client.rerank(
            query=query,
            documents=[self._document(hit) for hit in hits],
            model=self.model,
            top_k=None,
            truncation=True,
        )
        scores: list[float | None] = [None] * len(hits)
        for result in response.results:
            index = int(result.index)
            score = float(result.relevance_score)
            if not 0 <= index < len(hits) or scores[index] is not None:
                raise ValueError("Voyage reranker returned invalid document indices")
            if not isfinite(score) or not 0.0 <= score <= 1.0:
                raise ValueError("Voyage reranker returned an invalid relevance score")
            scores[index] = score
        if any(score is None for score in scores):
            raise ValueError("Voyage reranker did not score every document")
        reranked = []
        for hit, aligned_score in zip(hits, scores, strict=True):
            assert aligned_score is not None
            reranked.append({**hit, "rerank_score": aligned_score})
        return reranked


def create_voyage_reranker(
    *, api_key: str | None, model: str, timeout_seconds: float, max_retries: int,
) -> VoyageReranker | None:
    if not api_key:
        return None
    return VoyageReranker(
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )