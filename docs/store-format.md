---
title: Store format — Redthread's on-disk schema reference
description: The on-disk JSON/YAML schema for a Redthread memory store. It shows context entries, content-addressed artifacts, phase handoffs, and run records. Each schema has a version number for forward compatibility.
---

# Store format

This page shows the on-disk schema. The code for the schema is in
`src/redthread/models/`. Each schema has a `schema_version` field for
forward compatibility.

## project.yaml

```yaml
schema_version: 1
project_id: demo-app
name: null
phases: [build, test, present]   # your project's own pipeline
created_ts: "2026-07-09T12:00:00Z"
```

## ContextEntry

Each entry is one file that does not change:
`phases/<phase>/entries/<seq>-<entry_id>.json`.

The `entry_id` (a ULID) identifies the entry. The `seq` value is only for
information. Thus, when writers on different nodes write at the same time,
they do not use the same filename.

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

The `type` field has one of these values: `metric | decision | code_change
| artifact_ref | error | milestone | note`.

The `provenance` field is only metadata. Redthread does not use it to find
entries.

## Artifact

An artifact record is a content-addressed pointer. It does not contain the
data. The data is in `phases/<phase>/artifacts/...` (inline backend). The
record is also in `artifacts.index.json`.

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

The `backend` field has one of these values: `s3 | minio | rsync | gitlfs |
inline`.

- Redthread supports `inline` and `rsync` now. The `rsync` backend is a
  content-addressed directory. The directory can be local, mounted, or (in
  a future release) a real `rsync` target.
- Support for `s3`, `minio`, and `gitlfs` is planned.

For backends that are not inline, the `uri` authority
(`rsync://<name>/<sha256>`) is a **logical backend name**. On each machine,
`redthread backend set` maps this name to a local path. The store never
contains an absolute path.

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

The `key_results` field is a free-form dict. This is intentional. Put in it
the values that apply to your domain, for example `val_acc` for an ML run
or `coverage_pct` for an app build.

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

The `nodes` list records each machine that worked on the run. After you
replace a server, `redthread resume` uses this list.
