# Local unattended assurance

The `cpks assurance unattended` command observes the shared checkout and performs
a bounded routine check. Codex Scheduled Tasks is its optional scheduler and
review surface; the Python core has no dependency on Codex or another scheduler.
This document describes implementation and operation, not governance or authority.
Resolve current rule homes by stable ID through the live cp-wiki reader.

The standing scheduled scope is observe, check, write ignored technical evidence,
and report. It never grants permission to repair source, regenerate locks, install
dependencies, change hooks, stage/commit, write the Vault, work on Doing items, or
perform Project Control. Findings are candidates for a separately authorized task.

## Manual reproduction on this host

Use the existing locked project interpreter explicitly. Do not activate or fall
back to the old `.venv`, rebuild the environment, or install missing tools during
the routine. Paths below are this host's deployment settings, not core defaults.

```sh
/Users/cp/Developer/cpKnowledgeTools/artifacts/locking/environments/locked-final-20260831/bin/python -B \
  -m cp_knowledge_tools.cli.cpks assurance unattended \
  --repo-root /Users/cp/Developer/cpKnowledgeTools \
  --vault-root /Users/cp/Documents/cp-wiki \
  --project-path 'Projects/Internal/Kommunikations-Wissen verarbeiten und bereitstellen/Kommunikations-Wissen verarbeiten und bereitstellen.md' \
  --uv /Users/cp/Developer/cpKnowledgeTools/artifacts/locking/admission/uv-0.12.7/uv \
  --python /opt/homebrew/opt/python@3.14/bin/python3.14 \
  --environment /Users/cp/Developer/cpKnowledgeTools/artifacts/locking/environments/locked-final-20260831 \
  --cache-dir /Users/cp/Developer/cpKnowledgeTools/artifacts/locking/cache \
  --timeout 240 --command-timeout 45 --format text
```

The routine checks Git/input stability, live rule-home identity and integrity,
Project Home and Ready/Doing fingerprints, the Python pin, admitted uv, real
offline lock/environment consistency, local dependency inventory, scanner
bindings, hook-file fingerprints, and a fixed small deterministic fast scope.
It performs neither daily full regression nor network vulnerability scanning,
deep security scanning, fresh rebuilds, or human plausibility evaluation.
The fixed test baseline is `tests/assurance/test_project_environment.py`; Ruff
checks the assurance package. A routine pass is not full repository regression.
Defaults are 240 seconds for the cooperative total deadline and 45 seconds per
check. Repository/Vault traversal and bytes, subprocess output and evidence
discovery are separately bounded. A bound being reached remains incomplete.

`environment --mode routine_check` has a narrower claim than fresh rebuild:
consistency of the existing environment. Fresh creation is not applicable to
this cadence. The original `check`/`rebuild` contracts remain distinct.

## Result and evidence

| Result | Meaning | Exit |
| --- | --- | --- |
| `passed` | Required checks passed; no material delta, or first baseline created | 0 |
| `changed` | Required checks passed; material state changed | 0 |
| `incomplete` | Required evidence or execution is incomplete | 2 |
| `failed` | A required check or protected-input stability failed | 1 |

Materiality is `no_material_change`, `material_change`, or `action_required`.
An unchanged pre-existing dirty `AGENTS.md` is a stable observation. A new dirty
content/index/HEAD change, changed rules, queue, tool binding or check status is
compared explicitly. A stale lock or invalid tool/governance integrity requires
action. No numerical severity score or automatic repair is applied.

Reports live only in ignored `artifacts/assurance/scheduled/`. Unique UTC run IDs,
timezone-aware actual timestamps, validated schema/content hashes and predecessor
file hashes form a bounded append-only comparison history. Discovery does not
trust mtime or a mutable latest pointer. Missing first evidence creates a baseline;
corrupt or incomplete history produces an incomplete finding, never a false
"unchanged" claim. Prior reports are technical evidence, not authority.

The observer records fingerprints and limited metadata, not raw source/Vault
content, secrets, environment dumps, transcripts or scanner output. Before/after
fingerprints detect observed protected-input changes; they cannot attribute a
concurrent change to a particular process or prove absence of transient writes
that were reverted between observations. No reset or repair follows a mismatch.

Retention follows active `CPKS-SPEC-OPS`: keep evidence while review, audit or
reproduction needs remain. No automatic deletion occurs. The finite history
limit is an operational bound; inspect and deliberately archive a complete
history before the bound is reached, preserving required evidence. Partial
deletion breaks hash links and is reported.

## Native scheduled operation

Configured permanent task: **CPKS Daily Local Assurance**
(`cpks-daily-local-assurance`), daily **08:00 in the
host's local Europe/Berlin timezone**, against the actual shared checkout.
The time is an operational setting, not a governance rule. It does not create an
isolated clean worktree that would hide local dirty or staged state.

Native local runs require this host to be awake, the desktop app running and the
project available. Intended time is not an exact-start guarantee: the inspected
app applies scheduling jitter/ticks, and model/service/usage limits can delay or
prevent execution. There is no claim of cloud, always-on, catch-up, automatic
retry, or universal exactly-once execution.

The current supported native control surface inherits the project sandbox. On
this host that is `workspace-write` with tool/shell network access disabled.
The app tool offers no per-automation permission profile that restricts writes
to generated evidence alone. This is the smallest usable existing native mode
for evidence persistence, but it technically permits more local writes than this
task authorizes. The narrow instruction, bounded command and input comparisons
constrain/verify the operation; they are not an OS immutability guarantee.
No global/project permission settings are relaxed by this setup.
The verified native run reported a managed restricted filesystem and restricted
network, with `on-request` approval mode inherited on this host. It completed
without an approval interaction. Do not assume every scheduled runtime uses
`never`, or that an operation requiring approval will run unattended.

Network-off refers to the routine's tools and shell. The Codex agent still uses
OpenAI inference/services; therefore this is not a claim of no external processing.
MCP, app connectors and browser access have separate permission surfaces; the
scheduled instruction excludes those calls rather than claiming the shell
sandbox disables them globally.
The instruction requests only the command's minimized summary and does not ask
the agent to send source or Vault full texts to a provider. No credentials or
GitHub/PyPI/vulnerability-provider queries are needed by the routine.

Results appear in the desktop app's Scheduled surface. Material changes and
action-required findings need review; an unchanged successful result needs no
important alert. Native notification/archival behavior is product behavior and
does not turn an inbox receipt into a technical test pass. Inspect the linked
run evidence. Missing/failed native runs cannot be represented as successful
checks merely because the configuration exists.

The installed product additionally requires local automation `memory.md` under
its own app-state directory. The smoke run created that file outside the
repository. Keep this bookkeeping to time, run ID, status and evidence path;
never copy source, Vault text or reports into it. It is not the observer's
comparison history, governance, or an instruction to act on previous findings.
The validated repository evidence chain remains the comparison source. This
native bookkeeping is an additional product effect, so the complete native run
must not be described as writing only inside `artifacts/assurance/scheduled/`.

Use Scheduled → select the task → Edit/Pause/Delete to change or stop it, or ask
Codex to update the existing task by identity. Inspect existing tasks before
creating one; never create a second permanent overlapping schedule. A separate
explicitly identified one-shot test is removable test state, not a second daily
schedule. Do not change the daily task's cadence to simulate Run now.

Hook definitions remain guardrails, not scheduling or authority. Native
`hooks/list` can establish current trust/enablement; file fingerprints alone
cannot. Event execution must be observed separately, and unobserved event types
remain unknown. The runtime-neutral core does not invent a native trust receipt.
Its daily evidence therefore detects definition/script changes, but does not
detect a native trust or enablement toggle without a separate host observation.

## Reuse decision and product evidence

USE the installed native scheduled-task product and existing assurance primitives;
BUILD only the bounded observer and evidence composition. Reject a custom Python
scheduler, APScheduler/Temporal dependencies and parallel launchd scheduling.
launchd would require a separately assessed fallback only if native scheduling
cannot support the concrete scope. No package, copied source or scheduler runtime
was added to the project.

Current primary product documentation:
[Scheduled tasks](https://learn.chatgpt.com/docs/automations?surface=app) and
[Codex security](https://developers.openai.com/codex/security).
Installed-product inspection and actual run evidence are separately retained in
the implementation handover. Product configuration alone is `configured`;
`operationally verified` additionally requires a genuine native run, delivered
result, valid evidence and observed input stability.
