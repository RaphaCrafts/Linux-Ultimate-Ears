# Repository workflow

## Synchronize before editing

Before starting repository work, fetch the relevant remote (normally origin), inspect the current branch and upstream, working-tree changes, and ahead/behind or divergence status. Ensure the intended base includes the latest relevant remote changes before editing. Safely fast-forward a clean branch when appropriate. Preserve uncommitted changes and local commits; reconcile divergent work safely. Never discard work, reset destructively, or force-push to synchronize. If fetching fails or a conflict cannot be safely resolved, report the concrete blocker and do not claim the checkout is current.

## Commit and push every completed update

For every completed update to a repository, including code, tests, resources, configuration, documentation, and instructions, commit the task's changes and push to the intended remote branch before reporting completion. Group related edits into coherent commits. Preserve unrelated work and do not include secrets or unrelated changes. Re-fetch before pushing and safely reconcile concurrent remote changes. Verify the push succeeded. If a remote, credentials, branch permissions, or unresolved conflicts prevent pushing, report that limitation explicitly rather than claiming completion. Do not merge pull requests or force-push without separate authorization.

## Research scope

This project implements interoperability with Ultimate Ears speakers on Linux. Keep phone APKs, decompiled vendor sources, captures containing device identifiers, and downloaded analysis tools under ignored `.local/`. Commit original implementation, reproducible research scripts, and factual protocol documentation. Distinguish static evidence from hardware-verified behavior. Design the interface after understanding the control protocol.
