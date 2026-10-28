import json
from pathlib import Path

from chainlit.config import load_config

from chainlit_app import STARTER_PROMPTS, should_stream_draft


def test_modern_chat_theme_assets_and_configuration():
    theme = json.loads(Path("public/theme.json").read_text())
    css = Path("public/custom.css").read_text()
    config = load_config()

    assert config.ui.custom_css == "/public/custom.css"
    assert config.ui.default_theme == "light"
    assert config.ui.default_sidebar_state == "closed"
    assert config.ui.alert_style == "modern"
    assert config.ui.logo_file_url == "/public/leaf-mark.svg"
    assert Path("public/leaf-mark.svg").is_file()
    assert config.project.allow_origins == [
        "http://127.0.0.1:8000", "http://localhost:8000"
    ]
    assert config.features.spontaneous_file_upload.enabled is False
    assert config.project.session_timeout == 1800
    assert config.project.user_session_timeout == 86400
    for variant in ("light", "dark"):
        variables = theme["variables"][variant]
        assert variables["--primary"]
        assert variables["--background"]
        assert variables["--radius"] == "1rem"
    assert "--chat-width: min(100%, 52rem)" in css
    assert "#message-composer" in css
    assert "backdrop-filter: blur(18px)" in css


def test_starter_catalog_covers_enterprise_evaluation_scenarios():
    labels = [label for label, _ in STARTER_PROMPTS]
    messages = [message for _, message in STARTER_PROMPTS]

    assert len(STARTER_PROMPTS) == 12
    assert len(labels) == len(set(labels))
    assert len(messages) == len(set(messages))
    combined = " ".join(messages).lower()
    for topic in ("oauth", "prior authorization", "eligibility", "phi", "authority", "architecture"):
        assert topic in combined


def test_production_buffers_unverified_draft_tokens():
    assert should_stream_draft("local") is True
    assert should_stream_draft("production") is False