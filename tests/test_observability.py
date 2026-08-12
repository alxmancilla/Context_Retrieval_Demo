import io
import json
import logging

from core.observability import StructuredJsonFormatter, log_failure


def test_failure_log_is_structured_and_excludes_exception_text():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(StructuredJsonFormatter())
    logger = logging.Logger("cmm.test", level=logging.INFO)
    logger.addHandler(handler)

    log_failure(
        logger, "source_degraded", RuntimeError("sensitive raw error"),
        correlation_id="corr-123", node="retrieve_source", source="github",
        degraded="retrieve_github:RuntimeError",
    )

    rendered = stream.getvalue()
    payload = json.loads(rendered)
    assert payload["event"] == "source_degraded"
    assert payload["correlation_id"] == "corr-123"
    assert payload["exception_type"] == "RuntimeError"
    assert payload["source"] == "github"
    assert "sensitive raw error" not in rendered