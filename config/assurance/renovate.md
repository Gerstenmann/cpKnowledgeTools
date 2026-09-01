# Controlled dependency update automation

## Status and boundary

The repository contract is implemented locally. It is not remotely active and
does not grant merge, release, deployment, publication, supply-chain acceptance,
governance, or project authority.

Renovate is a dependency-change producer. A later update remains subject to the
normal path:

```text
upstream dependency delta
→ Renovate branch and pull request
→ Repository CI
→ human review
→ separately authorized merge
```

The only repository config is `.github/renovate.jsonc`. GitHub currently reports
`main` as the default branch, so the active remote config must eventually exist
on `main`. `useBaseBranchConfig: none` preserves that source rule.
`baseBranchPatterns` targets only `codex/source-to-knowledge-mvp` for update pull
requests.

## Initial repository contract

- Manager: only `pep621`.
- Enabled dependency types: `project.dependencies` and
  `project.optional-dependencies`.
- Disabled dependency types: `requires-python`, `build-system.requires`, and all
  other PEP 621 types through a default-deny package rule.
- Python artifact tool constraint: exactly `3.14.6`.
- uv artifact tool constraint: exactly `0.12.7`.
- GitHub Actions, pyenv, Docker, regex/custom and all other managers: disabled by
  the manager allowlist.
- Automerge: false globally and false in every merge-relevant rule.
- Pull request limits: two concurrent and one new pull request per hour.
- Pull request creation: immediate. CI starts after pull-request creation; there
  is no pre-PR status gate that could deadlock with pull-request-only CI.
- Dependency Dashboard: enabled. Major updates and weekly lock file maintenance
  require Dashboard approval.
- Normal update window: 07:00–11:00 on weekdays in `Europe/Berlin`.
- Lock file maintenance window: 07:00–11:00 on Monday, no more than weekly.
- GitHub vulnerability-alert remediation and OSV vulnerability alerts: disabled.
- Config migration, custom managers, post-upgrade commands and embedded
  credentials: absent or disabled.

The PEP621 manager recognizes `uv.lock` and delegates lock artifact changes to
the `uv` CLI. Renovate 44.53.0 selects `config.constraints.python` before the
project `requires-python` value, and `config.constraints.uv` before a
`tool.uv.required-version` value. The config therefore binds artifact execution
to Python 3.14.6 and uv 0.12.7 without making `.python-version`, Python, uv, the
build backend, or GitHub Actions update targets.

An artifact update that cannot produce a coherent `pyproject.toml` and `uv.lock`
pair is not acceptable. The first hosted job must show the actual selected tool
versions in its logs. If the hosted runtime does not honor uv 0.12.7, remote
activation stops.

## Minimum release age

Direct PyPI dependency updates use a strict three-day minimum release age. The
direct-update rule explicitly mirrors the effective behavior of Renovate
44.53.0's `security:minimumReleaseAgePypi` preset rather than importing a
mutable preset.

Renovate cannot validate Minimum Release Age for lock file maintenance because
the package manager selects transitive packages. The lock-maintenance rule sets
`minimumReleaseAge: null` and adds a pull-request note stating that limitation.
It intentionally has no datasource matcher because Renovate's synthetic
lock-maintenance update has no datasource; the manager and update-type matchers
keep the rule bounded to PEP621 lock maintenance. The same current upstream
limitation is represented for replacement, pin, bump, lockfile-update, and
rollback update types. No claim is made that every transitive package selected
by `uv lock --upgrade` is at least three days old.

## Research Gate and reuse decision

The bounded capability need was evaluated under `DEV-P05`, `DEV-P06`, and
`CPKS-POL-SW-SUPPLY`:

| Option | Fit and control | Runtime and credential cost | Disposition |
| --- | --- | --- | --- |
| Mend-hosted Renovate GitHub App | Native scheduling, Dashboard, branches, pull requests, PEP621 and uv support; repository config limits behavior | Broad GitHub App permissions and external source processing; Mend maintains runtime | `USE / WRAP`, accepted with conditions |
| Self-hosted Renovate in GitHub Actions | Repository-local schedule and inspectable workflow | Requires a write credential or separate App identity, action/runtime admission, workflow maintenance and external hosted-runner execution | Reject for the initial increment |
| Self-hosted Renovate as a dedicated GitHub App | Stronger identity and permission tailoring | App keys, installation tokens, scheduler, runner, upgrades, secrets and incident response become Owner operations | Reject for the initial increment |
| Local scheduled Renovate runner | Keeps execution on the Owner host and permits strong local inspection | Needs an always-available scheduler, protected GitHub write credential, Node/Containerbase maintenance and local incident handling | Reject for the initial increment |
| Manual dependency updates | Smallest third-party runtime and credential surface | High recurring Owner effort, no automated discovery/Dashboard and slower currentness | Retain as recovery path, not the target capability |

The hosted App is the smallest adequate operational path for this public GitHub
repository. The repository contract wraps its behavior with manager, dependency
type, tool-version, branch, approval, schedule, churn and no-automerge controls.
It is accepted only with these conditions:

1. install only for `Gerstenmann/cpKnowledgeTools`, never all repositories;
2. add no Renovate credential, repository secret, PAT, OIDC or provider token;
3. retain the manager and dependency-type allowlists;
4. observe the actual first job, effective config, selected Python/uv tools and
   every remote write;
5. stop and uninstall on scope, permission, credential, tool-binding or
   unexpected-write drift.

## Hosted App security and external processing

GitHub's current public App record for `github.com/apps/renovate` identifies
Mend as the owner and reports these permissions:

- read: administration, emails, members, metadata, packages, and vulnerability
  alerts;
- write: checks, contents, issues, pull requests, commit statuses, and workflows;
- events: issues, issue comments, pull requests, pull-request review comments,
  pushes, and repository events.

Those platform permissions are materially broader than the intended repository
behavior. Repository config narrows normal Renovate behavior, but it does not
technically remove GitHub App permissions. GitHub App permission is not CPKS,
merge, supply-chain, governance, project, release, or deployment authority.

Mend Renovate Cloud schedules jobs against installed repositories and executes
them on Mend job runners. Dependency extraction and artifact updates require the
runner to obtain and process repository source outside the Owner host. This is
external processing of repository content. The initial repository contains no
Owner source root, control root, knowledge root, production credentials or
secrets for Renovate. Installation remains a separate human-authorized action.
The hosted service's actual processing, log, cache and retention behavior must be
reviewed at activation and monitored; this local contract makes no private-cloud
or local-only processing claim.

## Validator and research runtime

The official local validation reference is Renovate `44.53.0`, released from
`renovatebot/renovate` commit `ea176510027cdcc6698e2f0fedb368c9ec159807`
under `AGPL-3.0-only`.

- npm artifact: `renovate-44.53.0.tgz`
- npm SHA-1: `01082d5e817fb009074bc31c7da590f6b791b434`
- locally observed SHA-256:
  `b20315b13d2c045b3a9be896901d12796a3f4d6e371e3473b8af3f6a074806c8`
- npm integrity:
  `sha512-ErROA8gizGDwA9p0roHp/ugXjuSfi/+RmI4wVxgU1f9j/Q4Xy696m2+hceegrrEjidJbHaEAtNGQJr7yMmHxkg==`
- execution: isolated temporary npm installation, Node 24, install scripts
  disabled, no global install, no project dependency and no committed runtime;
- network: npm download for the validator runtime and read-only registry lookups
  during extract/dry-run only;
- filesystem: temporary runtime plus a clean repository materialization;
- retention: transient validation evidence only, outside Git.

The isolated CLI resolves a large general-purpose runtime (601 installed npm
packages in the observed validation environment, including deprecated-package
warnings). This reinforces the decision not to adopt Renovate as a permanent
project dependency or local runtime.

The official strict validator accepted the repository config. A clean-tree
`platform=local` extract/dry-run then loaded `.github/renovate.jsonc`, resolved
`constraints.python` as 3.14.6 and `constraints.uv` as 0.12.7, selected only the
PEP621 manager, found only `pyproject.toml`, recognized 13 dependency records and
`uv.lock`, and kept `requires-python` and `build-system.requires` outside the
update set. It did not select GitHub Actions, pyenv, or a custom manager. The
lookup phase made eight read-only PyPI requests and found one major candidate;
the repository contract withheld it for Dashboard approval. No branch, pull
request, issue, or other remote write occurred.

Renovate's local platform stops before artifact mutation, including in full
dry-run mode, so it recognized the effective uv constraint but did not execute a
uv binary. Inspection of the same 44.53.0 PEP621 processor shows that artifact
updates pass `config.constraints.uv` to the `uv lock` tool constraint. The first
hosted job must still log actual uv 0.12.7 execution; any other or unknown
version is an activation stop condition. The isolated npm install omitted the
optional native RE2 module because install scripts were disabled, so validation
fell back to JavaScript RegExp. This config uses no regex or custom manager, and
that fallback did not expand the inspected filesystem or dependency scope.

The Mend-hosted App publishes that its Renovate version is maintained by the
service and may lag the open-source release by hours to about a week. Local
44.53.0 validation therefore proves this config against a concrete current
release, while remote acceptance still requires inspection of the actual hosted
version and effective config.

## Activation, observation, and recovery

Remote activation is a separate controlled sequence:

1. reread the remote development ref and fast-forward the local Renovate commit
   to `codex/source-to-knowledge-mvp`;
2. require Repository CI green on that exact commit;
3. reread `origin/main` and fast-forward the same commit to `main`;
4. install the Mend App only for `Gerstenmann/cpKnowledgeTools`, without added
   credentials or secrets;
5. inspect the first job, effective config, Dashboard and discovery before
   allowing one small non-major dependency proof.

For recovery, disable or uninstall the GitHub App and close bot-created branches,
pull requests or the Dashboard only under separate remote authority. Preserve
run and failure evidence before cleanup. Do not rewrite branch history or weaken
CI, tests, approvals, manager scope or tool constraints to obtain a passing run.

## Primary sources

- <https://docs.renovatebot.com/modules/manager/pep621/>
- <https://docs.renovatebot.com/configuration-options/>
- <https://docs.renovatebot.com/presets-security/>
- <https://docs.renovatebot.com/mend-hosted/overview/>
- <https://docs.renovatebot.com/mend-hosted/hosted-apps-config/>
- <https://docs.renovatebot.com/mend-hosted/job-scheduling/>
- <https://github.com/apps/renovate>
- <https://github.com/renovatebot/renovate/releases/tag/44.53.0>
