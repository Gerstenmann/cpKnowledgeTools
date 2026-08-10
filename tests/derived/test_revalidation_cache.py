from pathlib import Path

from cp_knowledge_tools.derived import RevalidationCache


def test_cache_reuses_only_exact_signature(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    cache = RevalidationCache(path)
    inputs = {"consumer": "A", "upstream": "B", "rule": "R1"}
    cache.put("A:B", inputs, {"result": "passed"})
    assert cache.get("A:B", inputs) == {"result": "passed"}
    assert cache.get("A:B", {**inputs, "rule": "R2"}) is None
    cache2 = RevalidationCache(path)
    assert cache2.get("A:B", inputs) == {"result": "passed"}
