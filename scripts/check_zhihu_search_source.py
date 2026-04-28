from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from knowledgeforge.agent.QueryEngine.tools.supplemental_sources import build_supplemental_source_targets, probe_source_url


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    query = " ".join(args).strip() or "Generative Adversarial Network"
    target = next(item for item in build_supplemental_source_targets(query) if item.key == "zhihu_search")
    result = probe_source_url(target)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.available else 1


if __name__ == "__main__":
    raise SystemExit(main())
