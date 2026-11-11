"""Group failures into clusters by normalised signature."""

from __future__ import annotations

from ..models import Cluster, TestResult
from .classifier import classify_message
from .signature import signature_for


def cluster_failures(results: list[TestResult]) -> list[Cluster]:
    groups: dict[str, list[TestResult]] = {}
    for result in results:
        if not result.outcome.is_failure:
            continue
        info = signature_for(result.message, result.trace)
        groups.setdefault(info.signature, []).append(result)

    clusters: list[Cluster] = []
    for signature, items in groups.items():
        items.sort(key=lambda item: item.round)
        sample = items[0]
        text = (sample.message or sample.trace or "").strip()
        if not text:
            text = f"{sample.outcome.value} (no message)"
        clusters.append(
            Cluster(
                signature=signature,
                label=classify_message(f"{sample.message}\n{sample.trace}"),
                count=len(items),
                first_round=items[0].round,
                last_round=items[-1].round,
                sample_message=" ".join(text.split())[:300],
            )
        )

    clusters.sort(key=lambda cluster: (-cluster.count, cluster.first_round))
    return clusters
