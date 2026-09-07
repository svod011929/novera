from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_BRAND = ("G" + "FORT").lower()


def test_runtime_sources_contain_only_novera_brand() -> None:
    checked_roots = (PROJECT_ROOT / "delta_backend", PROJECT_ROOT / "frontend")
    text_suffixes = {".py", ".html", ".js", ".css", ".svg", ".json"}
    offenders: list[str] = []

    for root in checked_roots:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in text_suffixes:
                content = path.read_text(encoding="utf-8", errors="ignore").lower()
                if RETIRED_BRAND in content:
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == []
