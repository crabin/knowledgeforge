from __future__ import annotations

from knowledgeforge.models import RequestContext


DEFAULT_SUBDOMAINS = ["基础概览", "关键参与者", "近期动态"]


class ContextBuilder:
    def build(self, payload: dict[str, object]) -> RequestContext:
        domain = str(payload.get("domain", "")).strip()
        if not domain:
            raise ValueError("`domain` is required.")

        subdomains = self._normalize_list(payload.get("subdomains")) or DEFAULT_SUBDOMAINS
        focus_points = self._normalize_list(payload.get("focus_points")) or [
            "定义与边界",
            "核心实体",
            "近期变化",
        ]
        constraints = self._normalize_list(payload.get("constraints"))
        time_window = str(payload.get("time_window", "近 12 个月")).strip() or "近 12 个月"

        initial_strategy = [
            f"围绕 {domain} 的 {topic} 收集可追溯资料"
            for topic in subdomains
        ]

        return RequestContext(
            domain=domain,
            subdomains=subdomains,
            time_window=time_window,
            focus_points=focus_points,
            constraints=constraints,
            initial_strategy=initial_strategy,
        )

    @staticmethod
    def _normalize_list(value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, list):
            items = value
        else:
            return []
        return [str(item).strip() for item in items if str(item).strip()]
