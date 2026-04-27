from __future__ import annotations

import importlib.util
from pathlib import Path

from agent.QueryEngine.tools.supplemental_sources import SourceProbeResult


ROOT = Path(__file__).resolve().parent.parent


def _load_script_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_tencent_cloud_source_script_returns_zero_when_available(monkeypatch, capsys) -> None:
    module = _load_script_module("check_tencent_cloud_source", "scripts/check_tencent_cloud_source.py")
    monkeypatch.setattr(
        module,
        "probe_source_url",
        lambda target: SourceProbeResult(
            key=target.key,
            url=target.url,
            available=True,
            status_code=200,
            http_status_code=200,
            final_url=target.url,
            probe_method="http",
            reason="ok",
            content_chars=128,
        ),
    )
    assert module.main(["GAN"]) == 0
    assert '"available": true' in capsys.readouterr().out.lower()


def test_check_zhihu_search_source_script_returns_one_when_blocked(monkeypatch, capsys) -> None:
    module = _load_script_module("check_zhihu_search_source", "scripts/check_zhihu_search_source.py")
    monkeypatch.setattr(
        module,
        "probe_source_url",
        lambda target: SourceProbeResult(
            key=target.key,
            url=target.url,
            available=False,
            status_code=200,
            http_status_code=200,
            final_url=target.url,
            probe_method="http",
            reason="blocked_marker_detected",
            content_chars=64,
        ),
    )
    assert module.main(["GAN"]) == 1
    assert "blocked_marker_detected" in capsys.readouterr().out


def test_check_zh_wikipedia_source_script_returns_zero_when_available(monkeypatch, capsys) -> None:
    module = _load_script_module("check_zh_wikipedia_source", "scripts/check_zh_wikipedia_source.py")
    monkeypatch.setattr(
        module,
        "probe_source_url",
        lambda target: SourceProbeResult(
            key=target.key,
            url=target.url,
            available=True,
            status_code=200,
            http_status_code=200,
            final_url=target.url,
            probe_method="http",
            reason="ok",
            content_chars=256,
        ),
    )
    assert module.main(["GAN"]) == 0
    assert "zh_wikipedia" in capsys.readouterr().out
