"""Analysis: scoring, signatures, clustering and classification."""

from .analyzer import analyze, ordered_tests_from
from .classifier import classify_message
from .cluster import cluster_failures
from .scorer import classify_outcome, compute_score
from .signature import normalize_text, signature_for

__all__ = [
    "analyze",
    "ordered_tests_from",
    "classify_message",
    "cluster_failures",
    "classify_outcome",
    "compute_score",
    "normalize_text",
    "signature_for",
]
