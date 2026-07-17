"""Example ML pipeline, phase 2: eval.

Consumes ONLY train's handoff — never train's raw entries — per the
handoff-contract rule. Downstream code never has to know how train chose to
log its metrics internally.
"""

from pathlib import Path

from redthread.adapters.base import PhaseAdapter
from redthread.store import LocalStore


def run_eval(store: LocalStore, run_id: str, code_dir: Path | None = None) -> None:
    with PhaseAdapter(store, run_id, "eval", code_dir=code_dir) as adapter:
        train_handoff = adapter.upstream("train")
        val_acc = train_handoff.key_results.get("val_acc", 0.0)

        adapter.log_note(consumed_from="train", train_headline=train_handoff.headline)
        test_acc = round(val_acc - 0.01, 4)  # small train/test gap
        adapter.log_metric(test_acc=test_acc)

        adapter.publish_handoff(
            headline=f"eval complete, test_acc {test_acc:.2f}",
            key_results={"test_acc": test_acc},
            open_questions=["overfitting after the last epoch?"],
        )
