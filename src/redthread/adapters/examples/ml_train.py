"""Example ML pipeline, phase 1: train.

Demonstrates PhaseAdapter usage for a training loop. This file is the only
place words like "epoch" or "val_acc" appear — the core has no idea what a
training run even is.
"""

from pathlib import Path

from redthread.adapters.base import PhaseAdapter
from redthread.store import LocalStore


def run_training(store: LocalStore, run_id: str, code_dir: Path | None = None) -> None:
    with PhaseAdapter(store, run_id, "train", code_dir=code_dir) as adapter:
        adapter.log_decision("switched to cosine LR schedule after plateau at epoch 6")

        best_val_acc = 0.0
        for epoch in range(3):
            val_acc = 0.80 + epoch * 0.03
            train_loss = 0.50 - epoch * 0.10
            adapter.log_metric(epoch=epoch, val_acc=val_acc, train_loss=train_loss)
            best_val_acc = max(best_val_acc, val_acc)

        adapter.set_summary(f"# train summary\n\nBest val_acc {best_val_acc:.2f}.\n")
        adapter.publish_handoff(
            headline=f"training complete, best val_acc {best_val_acc:.2f}",
            key_results={"val_acc": best_val_acc, "epochs": 3},
            decisions=["switched to cosine LR schedule after plateau at epoch 6"],
        )
