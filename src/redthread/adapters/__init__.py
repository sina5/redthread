"""Phase adapters: the only place domain-specific knowledge is allowed to
live. `base.PhaseAdapter` is generic; `examples/` holds two thin pipelines
(ML train/eval, app build/test) proving the same core serves both.
"""

from redthread.adapters.base import PhaseAdapter

__all__ = ["PhaseAdapter"]
