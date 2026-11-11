"""Probe budget: the guard rail that keeps locate from running forever."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProbeBudget:
    max_probes: int = 60
    used: int = 0

    def can_probe(self) -> bool:
        return self.used < self.max_probes

    def consume(self) -> None:
        self.used += 1

    @property
    def exhausted(self) -> bool:
        return self.used >= self.max_probes

    def __str__(self) -> str:
        return f"{self.used}/{self.max_probes}"
