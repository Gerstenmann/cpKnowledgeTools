# Local Codex launch profiles

The repository default is workspace-write, network disabled, and on-request
escalations routed to auto-review. Owner-requested Vault filesystem capability
is explicit; it grants no authority to mutate arbitrary Vault objects. The
read-only MCP remains the preferred governance resolution surface.

Native Codex 0.147.0 profiles live in `$CODEX_HOME/<name>.config.toml`, normally
`~/.codex/`. The adjacent files are versioned templates. They are not loaded
merely by being in this directory. Do not use legacy `[profiles.*]` tables.
On the 2026-08-31 enablement host, all three templates were copied without
overwriting existing files to `/Users/cp/.codex/` and byte-compared successfully.
This is installation evidence, not proof of effective permissions in this task.

Project configuration has higher precedence than native named profiles. These
explicit CLI flags work without installing profile files and preserve the
required mode even inside this repository:

```sh
codex --sandbox read-only -c web_search='"disabled"'
codex --sandbox workspace-write -c web_search='"disabled"'
codex --sandbox read-only -c web_search='"live"'
```

If profiles are installed, add `--profile cpks-audit`, `--profile
cpks-engineering` or `--profile cpks-research` respectively; retain the explicit
sandbox/web-search overrides above. The research role is instructed to use
primary sources. This is not a network domain allowlist. A host/proxy-managed
allowlist remains separate; no unrestricted shell networking is enabled here.

Three repository-local agent definitions are in `.codex/agents/`. Each requests
read-only sandboxing and inherits the model. Their instructions prohibit writes,
installation and external effects. They are development roles, not a product
agent runtime or a substitute for required human review.

Configuration reload/new-task startup is required to verify effective discovery,
sandbox permissions and agent roles. Editing config cannot change permissions
of an already running task. Global config and exact-hash hook trust are not
changed by these templates.

Synchronous hooks remain an explicit follow-up: Codex requires Owner trust via
`/hooks` for non-managed hook definitions. Do not manufacture trust. A shell
deny-list does not cover hosted tools, arbitrary Python or later terminal input,
and a Stop hook cannot safely distinguish this task's scope from concurrent
foreign work without a session-bound evidence contract. No placeholder security
hook is advertised as enforcement.

`config/assurance/codex-output.schema.json` can be passed to `codex exec
--output-schema`; `--json` separately emits event JSONL. No nested model run,
scheduled task, remote CI, push or PR is enabled by this configuration.

Sources verified against installed CLI help and current official documentation:
[profiles](https://learn.chatgpt.com/docs/config-file/config-advanced),
[subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents),
[auto-review](https://learn.chatgpt.com/docs/sandboxing/auto-review),
[hooks](https://learn.chatgpt.com/docs/hooks),
[structured execution](https://learn.chatgpt.com/docs/non-interactive-mode).
