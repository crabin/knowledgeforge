from __future__ import annotations

import json
import re
from typing import Any


CONTRACT_HEADING = "## 知识文件合同"
CONTRACT_BLOCK_PATTERN = re.compile(
    r"## 知识文件合同\s+```json\s*(\{.*?\})\s*```",
    re.DOTALL,
)


def render_contract_block(contract: dict[str, Any]) -> str:
    payload = json.dumps(contract, ensure_ascii=False, indent=2)
    return "\n".join([CONTRACT_HEADING, "", "```json", payload, "```"])


def parse_contract_block(text: str) -> dict[str, Any] | None:
    match = CONTRACT_BLOCK_PATTERN.search(text)
    if match is None:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def replace_contract_block(text: str, contract: dict[str, Any]) -> str:
    block = render_contract_block(contract)
    if CONTRACT_BLOCK_PATTERN.search(text):
        return CONTRACT_BLOCK_PATTERN.sub(block, text, count=1)
    suffix = "" if text.endswith("\n") else "\n"
    return f"{text}{suffix}\n{block}\n"
