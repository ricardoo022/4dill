---
name: scan-fase-0
description: Execute FASE 0 - Detect backend type and derive scan path from real response patterns.
---

# FASE 0 - Backend Detection

Use HTTP response patterns, script references, and endpoint behavior to classify target backend.

## Detection Workflow

1. Inspect HTML for framework markers (`__NEXT_DATA__`, `_app/immutable`, `wp-content`).
2. Inspect JS bundles for backend provider signatures (Supabase URL/key patterns, Firebase config).
3. Probe common API paths and parse headers/status codes.
4. Return backend profile with confidence and recommended `scan_path`.

## Output Contract

- Include backend type, confidence, and evidence snippets.
- Include next phases with rationale.
- Keep findings actionable for downstream scanner subtasks.
