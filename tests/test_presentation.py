from pathlib import Path

from ui.presentation import solution_architecture_markdown


def test_solution_architecture_markdown_contains_visual_and_implementation_map():
    diagram = solution_architecture_markdown()
    assert "```mermaid" in diagram
    assert "LangGraph coordinator" in diagram
    assert "Parallel retrieval tools" in diagram
    assert "evidence only" in diagram
    assert "Atlas hybrid search" in diagram
    assert "MongoDB memory nodes" in diagram
    assert "Implementation map" in diagram


def test_solution_architecture_png_asset_exists():
    asset = Path("public/solution-architecture.png")
    assert asset.exists()
    assert asset.read_bytes().startswith(b"\x89PNG")