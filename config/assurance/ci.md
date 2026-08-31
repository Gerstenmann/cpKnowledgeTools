# Repository CI — local materialization

**CI_IMPLEMENTED_LOCALLY** is the intended delivery state of this increment.
The workflow is not remotely activated, operationally verified or a required
branch gate merely because its file exists. A separate Owner authority must
cover the concrete push and first GitHub run. No repository settings are changed.
Technical verification does not grant governance, review, publication, release,
deployment or Project acceptance authority.

## Design and reuse decision

Research Gate: **required** under live `DEV-P05`, `DEV-P06` and
`CPKS-POL-SW-SUPPLY`. The Owner CI instruction authorizes local implementation
and a scoped commit only. Engineering/output/security/testing boundaries use
`CPKT-SPEC-ARCH`, `CPKS-SPEC-OPS`, `CPKS-SPEC-SEC`, `CPKS-SPEC-TST` and `DEV-P04`.
These references route to live rules; this document is not their replacement.

| Option | Disposition and tradeoff |
| --- | --- |
| GitHub Actions with three setup actions | USE platform, WRAP actions: established upstream releases and small integration boundary; adds an independent Linux host without another CI service. |
| GitHub shell workflow with custom download/setup | REJECT: would own authentication, platform selection, archive validation, Python installation and cleanup without improving the required test contract. |
| Another CI platform | REJECT for this increment: new account/permissions/configuration and migration cost, no demonstrated functional or architectural advantage. |
| Local Scheduled Assurance alone | KEEP for local workspace/control observation; insufficient for independent verification of a remote commit. |
| Existing PyYAML/UniqueKeyLoader, pytest, Ruff, Mypy, uv | USE: safe duplicate-key parsing and existing verification primitives; no new project dependency. |
| actionlint | LEARN/REJECT adoption: useful broader Actions diagnostics, but another separately admitted executable cannot replace the narrow security contract. No installation. |

The comparison considers functional and architectural fit, integration API,
complexity, maturity, maintenance, dependencies, licensing, provenance, security,
testability, rebuildability, exit, integration/maintenance cost and productization.
Actions fit the existing GitHub repository and have separate replaceable setup
boundaries; commands remain locally runnable. No upstream source is copied,
vendored or redistributed. MIT actions and MIT OR Apache-2.0 uv do not decide
the project's outbound license. The representative set is deliberately bounded
to the four requested approaches plus an optional validator candidate.

The Standard Operation Registry was inspected: its seven governance/artifact/
derived/incident operations do not support CI orchestration. Existing assurance
repository inspection requires a named branch, while Actions checkout is detached;
its uv binary admission is Darwin/arm64-specific. Therefore `scripts/ci/` owns
this small repository orchestration, using the same underlying tools. It is not
a new product architecture domain or a general Actions interpreter.

## Action and tool admission

[ci-actions.json](ci-actions.json) is the separate enduring CI admission role.
It records exact upstream commits, releases, MIT licenses, Node 24 runtime,
privileges, provenance, conditions and replacement boundaries for each action.
On 2026-08-31 the official release APIs and direct tag refs matched those SHAs;
GitHub reported valid commit verification for all three. Checkout's release was
not immutable; the full commit pin remains mandatory. setup-python/setup-uv
releases were marked immutable. Signatures are not proof of software safety.

The pinned setup-uv action does not include uv 0.12.7 in its embedded checksum
table. The explicit Linux archive SHA256 is mandatory and was cross-checked
against the official release asset digest and Astral versions manifest. The
archive is checked before extraction; a hosted tool-cache hit bypasses download
verification. No independent binary reproduction is claimed. Exact uv 0.12.7 is
also checked at runtime. The Darwin binary stays in its existing admission.

Runner: **ubuntu-24.04**, Linux x64, one job, 30 minutes, no matrix/container/
self-hosted runner. Upstream Node 24 actions require runner >=2.327.1.
The inspected runner image already carries Python 3.14.7; setup-python can obtain
the exact **3.14.6** from `actions/python-versions`. The Python pin is read from
`.python-version`; check-latest is false, no free-threaded/prerelease request.
Runtime checks print sys.version, implementation, architecture and SOABI, and
reject a mismatch. setup-python has no Python archive checksum input. Its
distribution is not byte-identical to Homebrew. First Linux execution is pending.

## Security and execution limits

- Only push/PR against `codex/source-to-knowledge-mvp`, plus workflow_dispatch.
  Dispatch is only delivered when the file exists on the default branch; do not
  change `main` or repository defaults just to enable it in this increment.
- Explicit `contents: read` means all unspecified token permissions are `none`.
  Actions may access the ephemeral job token, including checkout/API downloads.
  No custom secrets, PAT, App credential, OIDC, write permission or privileged
  PR trigger is used. Fork PR code remains untrusted, running without secrets
  or write token; later policy must not enable write tokens for fork PRs.
- Checkout depth 1 is sufficient: Git-dependent tests build synthetic temporary
  repositories. No submodules/LFS. `persist-credentials:false` removes checkout
  authentication before repository commands; the pinned action also has cleanup.
- No cross-run uv/Python/dependency cache restore/save, no artifact upload.
  Hosted image/tool caches still exist; per-job uv files under ignored
  `artifacts/ci/cache` disappear with the ephemeral runner. No action source or
  executable is committed.
- Actions require GitHub API/download/runner communication. Locked sync may
  contact PyPI and files.pythonhosted.org; the Astral download mirror is disabled.
  Standard hosted VMs have ambient Internet access and passwordless sudo.
  These are **not** firewall-enforced egress restrictions. Least privilege here
  means no sensitive Owner inputs, no reusable credentials, read-only GitHub
  token, fixed commands and finite lifetime; it is not an OS sandbox claim.
- uv Python downloads/managed discovery are disabled before setup-uv, including
  its `uv python find`, and in all uv commands. No self-update or scanner install.
- CI uses repository source/tests/fixtures/configuration only. It does not resolve
  `cpks.control`, read `cpks.knowledge`/`cpks.sources`, inspect Project Work Items
  or mutate governance. Synthetic governance fixtures remain valid test inputs.
  Command subprocesses do not inherit Owner-root, scanner, token or uv overrides.
- Native hook protocol tests additionally need `/usr/bin/python3` and Git; they
  do not attest native Codex hook trust or replace the locked project interpreter.
- Existing isolated editable-build requirements (`setuptools>=68`, `wheel`) are
  outside uv.lock. `--no-build` still permits the first-party editable backend.
  This inherited limitation is explicit, not a hermetic-build claim. Compare
  actual backend versions on first remote activation with the existing admission
  (setuptools 84.0.0, wheel 0.48.0); review a material delta before operational
  acceptance. No hidden CI-only constraints or lock rewrite are introduced.

## Commands and local reproduction

GitHub executes `python -I -B scripts/ci/verify.py --host linux` after setup.
The tested `commands()` function in that script is the single command inventory:

1. `uv lock --check --offline`, with explicit Python, PyPI and no-config options.
2. `uv sync --locked --extra dev --no-build` into an absent `.venv`.
3. `uv pip check` against that exact environment.
4. Verify environment Python identity, then run the closed workflow checker.
5. Rebuild the synthetic E2E prerequisite with the existing
   `scripts/cp_tools/run_minecraft_esports_mvp.py --output-root
   artifacts/tests/source_to_knowledge/experience-v1-2-final-validated`.
   Its three tracked synthetic HTML inputs produce the projection/publication
   files required by continuation and enrichment tests. No old artifact is copied
   and no Golden is used as generator input. CI requires the output to be absent.
6. Full `pytest tests -q -p no:cacheprovider`, including Frontier/Assurance/hooks.
7. Scoped Ruff: Frontier, Assurance source/tests, hooks, and the new CI files.
8. Existing Mypy profiles: Frontier with skipped imports; Assurance and CI scripts
   with skipped imports and missing-import tolerance.
9. `git diff --check`; finally compare input bytes/modes, index, HEAD and status even
   after a failing command. A mutation fails visibly without automatic reset.

For an already verified local locked environment, from the verified repository:

```sh
<locked-project-python> -B scripts/ci/verify.py --host local \
  --uv <absolute-admitted-uv> --environment <absolute-locked-environment> --existing
```

This invokes the same repository commands. Sync adds `--check --offline`:
it proves existing consistency and does not claim a fresh build. Existing local
synthetic baseline outputs are preserved, with that preparation step explicitly
reported as not rebuilt. The full fresh CI command sequence is also reproducible
in an isolated checkout with absent environment/baseline targets. A separately
authorized local fresh rebuild omits `--existing`; `--offline` may use a separately
prepared admitted uv cache under that checkout's ignored `artifacts/ci/cache`.
No local cached replay establishes a clean Linux download or a hermetic build.
The local host guard cannot establish Linux execution or Actions orchestration.

Known exclusions: global Ruff E501 debt in the template generator and the missing
PyYAML stub under a stricter global Mypy profile are not newly invented gates.
No `continue-on-error`, blanket lint ignore, Golden change or test-count threshold
is used. The five real-scanner opt-in skips remain visible; no scanners run in CI.
New errors inside the scoped profiles fail. Scope expansion requires review.

The closed validator rejects any additional jobs, steps, permissions, triggers,
environment, mutable refs, arbitrary shell or setup options. It is a regression
guard in the same repository trust domain, not an adversarial policy engine that
can defend itself against a PR replacing both validator and tests. Action/SHA
changes require fresh upstream provenance/admission review; local parsing cannot
establish remote provenance or enforce GitHub settings.

Scheduled Assurance is unchanged and remains separate local/control evidence.
WP-004, model/provider/prompt/inference work and Golden semantics are untouched.
Baseline disposition: **baseline_review_candidate** for local engineering
enablement; not an operational remote-CI capability and no Baseline mutation.

## Official primary evidence

- [GitHub secure use and full-SHA guidance](https://docs.github.com/en/actions/reference/security/secure-use)
- [GITHUB_TOKEN permissions](https://github.com/github/docs/blob/main/data/reusables/actions/github-token-available-permissions.md)
- [Fork secrets](https://github.com/github/docs/blob/main/data/reusables/actions/forked-secrets.md)
- [Dispatch default-branch restriction](https://github.com/github/docs/blob/main/data/reusables/actions/workflow-dispatch.md)
- [Hosted runner capabilities and egress](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Inspected Ubuntu image](https://github.com/actions/runner-images/blob/be22fc2981aa0e7b5c194a6cee295ae749727c04/images/ubuntu/Ubuntu2404-Readme.md)
- [Exact Python availability](https://github.com/actions/python-versions/blob/72b9d3979c59eb161800043c4736f56102a07b27/versions-manifest.json)
- [uv download checksum behavior](https://github.com/astral-sh/setup-uv/blob/20cfd1bf945f4377ade1205e4dbc17946fc9a30d/src/download/download-version.ts)
- [Astral versions manifest](https://github.com/astral-sh/versions/blob/4bca9ba5cee45770c16e719d8248f03594c9087a/v1/uv.ndjson)
- [uv locked sync](https://github.com/astral-sh/uv/blob/61291a8ca5477a9ca653f14d2ac5665587c263fa/docs/concepts/projects/sync.md)
- [actionlint candidate](https://github.com/rhysd/actionlint)

Release, license and immutable source links for every action are in the admission
JSON. Research inspected selected source paths and official metadata, not every
bundled JavaScript dependency or a vulnerability database. Those limitations
remain explicit; no scanner cleanliness or complete third-party audit is claimed.
