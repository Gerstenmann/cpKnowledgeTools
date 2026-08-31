# Local Codex lifecycle hooks

These four synchronous hooks add local observations and a few deterministic
guardrails. They do not resolve governance, grant authority, roll back effects,
or replace the sandbox, filesystem permissions, network controls and approvals.
Hook allow is not authority; hook pass is not verification. Existing dirty work
does not prove foreign ownership. Resolve live rule homes through the normal
agent guidance before material work.

## Runtime and trust

Implemented against **Codex CLI 0.147.0**, with native `hooks` enabled by default.
Codex discovers `../hooks.json` alongside the project's active config layer.
There are no inline hooks or PermissionRequest handlers; `config.toml` is unchanged.
The existing local macOS runtime supplies `/usr/bin/python3` (3.9.6 or newer)
and `/usr/bin/git`. No active venv, package install, MCP connection or network is
needed. Other platforms must explicitly verify these paths and POSIX primitives.

The inline launcher resolves the Git root from the actual process cwd, including
subdirectories. It opens the fixed script without following symlinks and executes
only the bounded bytes whose SHA-256 matches the literal in the definition.
This matters because native Codex trust hashes the **definition**, not referenced
script bytes. After editing `guard.py`, update `expected` in all four commands and
review both files. Do not change trusted hashes or bypass native trust. The
launcher executes the verified bytes directly; it does not reopen the script.
Hash mismatch or launcher failure is a hook error, not a security boundary.

Native discovery does not mean activation. When Codex reports pending trust, the
Owner opens this project, enters **`/hooks`**, reviews the four definitions and
script, and uses the native Trust action. Start a new session afterwards. An agent
must not trust its own definition. Tests invoke the command directly in synthetic
repositories; they do not establish native trust or prove native event delivery.

## Behavior

| Event | Behavior |
| --- | --- |
| SessionStart | Resolve root, branch, HEAD, initial dirty paths and file fingerprints. Resume/compact preserve a readable session baseline. Missing/corrupt evidence is reconstructed as unknown. |
| PreToolUse | Block literal Owner Direct execution and narrowly identified destructive commands; warn about remote effects, uncertain shell syntax and edits overlapping initial dirty paths. |
| PostToolUse | Compare file contents and Git-relevant executable bits, including further edits to already dirty files; report overlap without assigning ownership. Observe verification candidates, never store their output. |
| Stop | Once per newly observed content generation, remind the agent to run or confirm narrow verification. Honor `stop_hook_active`; initial dirtiness, staging, a commit, no commit or no full suite do not themselves trigger it. |

Hard denials cover literal executable `--owner-direct` arguments (including simple
literal `sh/bash/zsh -c` wrappers), an explicit top-level runtime input
`authority_mode: human_owner_direct`, `git reset --hard`, potentially deleting
`git clean` (dry-run/help excluded), and recursive `rm` of an explicit absolute
repository root, `/`, or a configured additional writable root. Search/echo and
patch text mentioning these commands are not executable requests.

Additional roots are read only from this repository's existing single-line,
JSON-compatible `sandbox_workspace_write.writable_roots` array. This is deletion
target metadata, not authority. Other TOML spellings/global configuration,
symlink aliases and relative deletion targets are outside that check. Codex 0.147
does **not** include an exec request's `workdir` in hook input; hook cwd cannot prove
where a relative deletion would execute. Such deletion is advisory.

`git push`, common `gh pr merge`/release, package publish, Docker push and selected
deployment commands are **advisory**, because later separate Owner authority can
legitimately authorize them. No agent-set bypass variable, approval file or
authority marker exists. Native `permissionDecision: ask` is not usable in 0.147:
it becomes a failed hook, not an approval request. Normal approvals remain primary.

The shell classifier intentionally handles only literal words, separators and
limited wrappers. Variables, substitutions, redirections, here-documents, functions,
aliases, indirect scripts and other complex syntax are not reliably classified.
An unknown or unmatched command is never an authorization or safety conclusion.

## Verification limitation in 0.147

The actual Bash PostToolUse response is aggregated/truncated output text. It has
no reliably bound exit code. Therefore pytest, Ruff check, mypy and existing
`cpks assurance verify` candidates are recorded with **outcome `unknown`**.
Neither `passed`, a JSON-looking stdout value nor an invented `exit_code` field
proves success. There is deliberately no success parser or agent-set receipt.
Even a genuinely passing run can receive the one-time Stop reminder: confirm its
actual result in the task, then complete. This hook cannot implement automatic
“mutation + proven verification => no reminder” with the installed wire contract.
It never forces a full suite or repeatedly blocks the same content generation.

## Temporary evidence and limits

State lives in `/tmp/cpks-codex-hooks-<uid>/` (macOS resolves `/tmp` to
`/private/tmp`). Filenames hash session ID and root. The directory is private
0700; JSON and lock files are 0600, with nonblocking locks and atomic replacement.
Only roots, paths, branch/HEAD, timestamps, content hashes, counters and a
verification kind/outcome are retained. No transcript, prompt, environment dump,
source text, command or tool output is retained. Paths themselves remain local
metadata; do not export the temp directory as a report.

Retention is temporary OS-managed cleanup, with **no guaranteed expiry** or
repository retention promise. It may survive a process restart so resume works.
It is safe to remove a finished session's JSON/lock after all its hooks exit;
never remove an active lock. Missing/unsafe/contended state yields unknown evidence.
This mutable local evidence is not a tamper-resistant audit or source of truth.

Each command has a 10-second Codex timeout. Git calls have 2-second timeouts;
retained JSON/Git output is bounded to 2 MiB, snapshots to 10,000 files, 8 MiB per
file and 64 MiB total. Ignored files are not observed. Symlinks, submodules,
oversize files and incomplete reads make the snapshot unknown. Concurrent changes
cannot be attributed to one tool; observations are not an atomic Git transaction.
Git output spools to temporary disk; hard resource quotas remain a host concern.

PreToolUse uses `*` to see explicit structured runtime modes; other observations
cover Bash/exec, apply_patch/Edit/Write. MCP/local functions have native names, but
arbitrary nested inputs are not parsed as shell. `write_stdin` does not rerun Pre;
specialized and hosted paths may bypass normal hooks entirely. Native errors,
timeouts or invalid output can fail open. PostToolUse cannot undo an effect.

## Validation and maintenance

From the Git root, using the verified project interpreter:

```sh
.venv/bin/python -m pytest tests/hooks tests/assurance -q
.venv/bin/python -m ruff check --target-version py39 .codex/hooks/guard.py
.venv/bin/python -m ruff check tests/hooks
.venv/bin/python -m mypy --follow-imports skip --check-untyped-defs .codex/hooks/guard.py
git diff --check
```

Use native app-server `hooks/list` for read-only discovery; no model turn or trust
mutation is required. Revalidate against the installed release before changing
the event protocol, especially verification and blocking behavior.

Internal reuse: Git environment isolation, content fingerprints and no-follow
reads follow existing assurance/reuse helpers. Direct imports would require the
product's Python 3.14 environment; this standalone Python 3.9 adapter uses stdlib
only. The inspected Standard Operation Registry has no hook/session operation.
No third-party framework, copied upstream implementation or runtime dependency
was introduced.

Primary references: [official hooks guide](https://developers.openai.com/codex/hooks),
[0.147 schemas](https://github.com/openai/codex/tree/rust-v0.147.0/codex-rs/hooks/schema/generated),
[discovery/trust](https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/hooks/src/engine/discovery.rs),
[runtime cwd](https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/core/src/hook_runtime.rs),
[tool response](https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/core/src/tools/context.rs).
Release source takes precedence over newer examples in the current guide.
