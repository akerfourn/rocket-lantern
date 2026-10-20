"""Persist the optional counters and annotation categories of the summary overlay."""

import json
from dataclasses import asdict, dataclass

from rocket_lantern.label_catalog import LabelCatalog


@dataclass(frozen=True)
class SummaryOverlayContent:
    wins: bool = True
    losses: bool = True
    delta: bool = True
    label_lists: tuple[str, ...] = ()

    def has_content(self, catalog: LabelCatalog) -> bool:
        if self.wins or self.losses or self.delta:
            return True
        return any(item.id in self.label_lists for item in catalog.enabled_lists())

    def serialize(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True)


def parse_summary_content(value: str) -> SummaryOverlayContent:
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("Summary overlay content must be an object")
    counters = [data.get(key, True) for key in ("wins", "losses", "delta")]
    if any(type(value) is not bool for value in counters):
        raise ValueError("Summary overlay counter flags must be booleans")
    lists = data.get("label_lists", [])
    if not isinstance(lists, list) or any(not isinstance(item, str) or not item for item in lists):
        raise ValueError("Summary overlay categories must be nonempty strings")
    return SummaryOverlayContent(*counters, tuple(dict.fromkeys(lists)))
