"""Shared helper for the present family: gather every upstream handoff in
pipeline order, skipping phases that haven't published one yet.
"""

from redthread.models import Handoff
from redthread.store import LocalStore, StoreError


def collect_handoffs(store: LocalStore, run_id: str, phase: str) -> list[Handoff]:
    if phase not in store.manifest.phases:
        raise StoreError(
            f"phase {phase!r} is not in this project's pipeline {store.manifest.phases}"
        )
    upstream_phases = store.manifest.phases[: store.manifest.phases.index(phase)]
    handoffs = []
    for upstream_phase in upstream_phases:
        try:
            handoffs.append(store.get_handoff(run_id, upstream_phase))
        except StoreError:
            continue
    return handoffs
