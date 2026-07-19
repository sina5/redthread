---
title: Store format — Redthread's on-disk schema reference
description: The on-disk JSON/YAML schema for a Redthread memory store — context entries, content-addressed artifacts, phase handoffs, and run records, all versioned for forward compatibility.
---

# Store format

The on-disk schema, as implemented in `src/redthread/models/`. Every schema
carries `schema_version` for forward compatibility.

## project.yaml

```yaml
schema_version: 1
project_id: demo-app
name: null
phases: [build, test, present]   # your project's own pipeline
created_ts: "2026-07-09T12:00:00Z"
```

## ContextEntry

One immutable file per entry: `phases/<phase>/entries/<seq>-<entry_id>.json`.
`entry_id` (a ULID) is the real identity — `seq` is advisory only, so
concurrent writers from different nodes never collide on a filename.

```json
{
  "schema_version": 1,
  "entry_id": "01J8ZQ...",
  "run_id": "01J8ZK...",
  "phase": "build",
  "type": "decision",
  "ts": "2026-07-09T14:03:22Z",
  "provenance": {
    "node_id": "node-a3f",
    "host": "gpu-07.cluster",
    "agent": "claude-code@1.2",
    "project_git_sha": "9f2c1a"
  },
  "payload": {},
  "tags": [],
  "links": []
}
```

`type` is one of `metric | decision | code_change | artifact_ref | error |
milestone | note`. `provenance` is metadata only — never used for addressing.

## Artifact

A content-addressed pointer, not a payload:
`phases/<phase>/artifacts/...` (inline backend) plus an entry in
`artifacts.index.json`.

```json
{
  "schema_version": 1,
  "artifact_id": "app-bin",
  "kind": "build",
  "sha256": "e3b0c442...",
  "size_bytes": 1734000,
  "backend": "inline",
  "uri": "runs/01J8ZK.../phases/build/artifacts/app-bin.bin",
  "produced_by_phase": "build",
  "created_ts": "2026-07-09T14:20:00Z"
}
```

`backend` is one of `s3 | minio | rsync | gitlfs | inline`. `inline` and
`rsync` (a content-addressed directory — local, mounted, or a future real
`rsync` target) are implemented; `s3`, `minio`, and `gitlfs` are planned.
For non-inline backends, the `uri` authority (`rsync://<name>/<sha256>`) is a
**logical backend name**, resolved to a local path per-machine by
`redthread backend set` — never an absolute path in the store itself.

## Handoff — `phases/<phase>/handoff.json`

```json
{
  "schema_version": 1,
  "from_phase": "build",
  "run_id": "01J8ZK...",
  "headline": "build ok, 0 warnings",
  "key_results": {"warnings": 0},
  "best_artifacts": ["app-bin"],
  "decisions": ["..."],
  "open_questions": ["..."],
  "figures": ["..."]
}
```

`key_results` is a free-form dict by design — `val_acc` for an ML run,
`coverage_pct` for an app build, whatever the domain calls for.

## run.yaml

```yaml
schema_version: 1
run_id: 01J8ZK...
status: active
parent_run_id: null       # reserved for sweep/fork lineage
phases:
  build: pending
  test: pending
  present: pending
nodes:
  - node_id: node-a3f
    host: gpu-07
    joined: 2026-07-09T10:00:00Z
    left: null
created_ts: 2026-07-09T09:59:00Z
```

`nodes` records every machine that has touched the run — the basis for
`redthread resume` after a server swap.
