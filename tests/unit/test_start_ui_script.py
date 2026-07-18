from pathlib import Path


def test_start_ui_uses_current_local_defaults() -> None:
    script = (Path(__file__).parents[2] / "scripts" / "start-ui.ps1").read_text(
        encoding="utf-8-sig"
    )

    assert "[int]$WebPort = 53257" in script
    assert "AppData\\Local\\Programs\\Python\\Python310\\python.exe" in script
    assert "$env:PYTHONPATH = \"src\"" in script
