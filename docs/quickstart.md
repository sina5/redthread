---
description: Install Redthread and create a store, log context, and publish a phase handoff in under a minute.
---

# Quickstart

## Install

From PyPI:

```bash
pip install redthread          # or: uv tool install redthread
```

Or from a source checkout:

```bash
uv sync    # then prefix each `redthread` command below with `uv run`
```

## 60-second walkthrough

```bash
redthread init demo-app --phases build,test,present --store ./demo-store

run_id=$(redthread run start --store ./demo-store)

redthread log "$run_id" build note '{"msg": "kicked off build"}' --store ./demo-store

echo '{"headline": "build ok", "key_results": {"warnings": 0}}' > handoff.json
redthread handoff publish "$run_id" build handoff.json --store ./demo-store
redthread handoff get "$run_id" build --store ./demo-store

redthread read "$run_id" --store ./demo-store
```

See [Usage](usage.md) for the full command reference.

## Serve these docs locally

```bash
uv run --group docs mkdocs serve
```
