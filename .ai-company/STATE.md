# State Orientation

This file is orientation only. Do not use it to determine whether a task is queued, running, blocked, complete, reviewed, or mergeable.

Live operational state remains in:

1. the current GitHub Issue and its lifecycle labels and records;
2. the actual Draft PR, changed paths, and durable GitHub-visible review evidence;
3. fixed local test evidence and GitHub CI;
4. the existing worker's lifecycle recovery state where applicable; and
5. Issue #35 for persistent worker health and sanitized diagnostics.

Chat transcripts, local planning notes, and `.ai-company/` documents are not competing state stores. If they disagree with current durable GitHub and worker evidence, verify the durable records and correct the orientation material rather than creating a parallel lifecycle.
