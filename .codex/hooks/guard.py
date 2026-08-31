"""Small Codex 0.147 lifecycle adapter; advisory evidence, never authority."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

MAX_JSON = 2 * 1024 * 1024
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
LOCAL_TOOLS = {
    "Bash",
    "exec_command",
    "shell",
    "shell_command",
    "apply_patch",
    "Edit",
    "Write",
}


def context(event: str, message: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {"hookEventName": event, "additionalContext": message}
    }


def deny(message: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": message,
        }
    }


def git(cwd: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    # Disk spool bounds retained memory; host sandbox still owns resource limits.
    with tempfile.TemporaryFile() as output:
        subprocess.run(
            [
                "/usr/bin/git",
                "--no-optional-locks",
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(cwd),
                *args,
            ],
            env=env,
            stdout=output,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=2,
        )
        output.seek(0)
        data = output.read(MAX_JSON + 1)
    if len(data) > MAX_JSON:
        raise ValueError("Git output limit")
    return data.decode("utf-8", "surrogateescape")


def read_regular(path: Path, limit: int) -> bytes:
    """Do not follow symlinks in any component, including directory parents."""
    path = path.absolute()
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
        child = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
        )
        with os.fdopen(child, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise ValueError("Not a bounded regular file")
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            if (
                len(data) > limit
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
            ):
                raise ValueError("File changed during observation")
            return data
    finally:
        os.close(fd)


def snapshot(root: Path) -> dict[str, Any]:
    files = sorted(
        set(
            filter(
                None,
                git(root, "ls-files", "-co", "--exclude-standard", "-z").split("\0"),
            )
        )
    )
    if len(files) > 10000:
        raise ValueError("File count limit")
    hashes: dict[str, str] = {}
    total = 0
    for name in files:
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Unexpected Git path")
        try:
            data = read_regular(root / name, min(MAX_FILE, MAX_TOTAL - total))
            total += len(data)
            mode = (root / name).lstat().st_mode
            if not stat.S_ISREG(mode):
                raise ValueError("File type changed during observation")
            hashes[name] = hashlib.sha256(data).hexdigest() + (
                ":executable" if mode & stat.S_IXUSR else ":regular"
            )
        except FileNotFoundError:
            # Physical absence is identical before/after staging a deletion.
            pass
    records = iter(
        git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0")
    )
    dirty = []
    for record in records:
        if record:
            dirty.append(record[3:])
            if "R" in record[:2] or "C" in record[:2]:
                dirty.append(next(records))
    return {
        "root": str(root),
        "branch": git(root, "rev-parse", "--abbrev-ref", "HEAD").strip(),
        "head": git(root, "rev-parse", "HEAD").strip(),
        "dirty": sorted(set(dirty)),
        "files": hashes,
    }


def simple_commands(command: str) -> list[list[str]]:
    """Literal shell commands only. Complex shell syntax is deliberately unknown."""
    segments, start, quote, escaped, comment = [], 0, "", False, False
    word_start = True
    for i, char in enumerate(command):
        if comment:
            if char == "\n":
                comment, start = False, i + 1
                word_start = True
            continue
        if escaped:
            escaped = False
            word_start = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            word_start = False
        elif char == quote:
            quote = ""
        elif not quote and char in "\"'":
            quote = char
            word_start = False
        elif not quote and char == "#" and word_start:
            segments.append(command[start:i])
            comment = True
        elif quote != "'" and char in "$`":
            raise ValueError("Dynamic shell expression")
        elif not quote and char in "<>(){}":
            raise ValueError("Complex shell expression")
        elif not quote and char in ";&|\n":
            segments.append(command[start:i])
            start = i + 1
            word_start = True
        elif not quote:
            word_start = char.isspace()
    if quote or escaped:
        raise ValueError("Incomplete shell expression")
    if not comment:
        segments.append(command[start:])
    return [
        words for segment in segments if (words := shlex.split(segment, comments=False))
    ]


def unwrap(words: list[str]) -> list[str]:
    for _ in range(8):
        while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]):
            words = words[1:]
        if not words:
            break
        wrapper = Path(words[0]).name
        flags = {
            "env": {"-i", "--ignore-environment"},
            "command": {"-p"},
            "exec": {"-c", "-l"},
        }.get(wrapper)
        if flags is None:
            break
        tail = words[1:]
        while tail and tail[0] in flags:
            tail = tail[1:]
        if tail[:1] == ["--"]:
            tail = tail[1:]
        elif tail and tail[0].startswith("-"):
            break  # Query/complex wrapper options are not executable argv here.
        words = tail
    return words


def git_arguments(words: list[str]) -> list[str]:
    words = words[1:]
    while words and words[0].startswith("-"):
        if words[0] in {"-C", "-c", "--git-dir", "--work-tree"}:
            words = words[2:]
        elif words[0].startswith(("--git-dir=", "--work-tree=", "-C", "-c")):
            words = words[1:]
        else:
            return []
    return words


def protected_roots(root: Path) -> set[str]:
    roots = {str(root), "/"}
    # Narrow read of this repo's existing JSON-compatible TOML inline array.
    # Capability roots are deletion targets to protect, never authority grants.
    try:
        config = read_regular(root / ".codex/config.toml", 65536).decode()
        section = config.split("[sandbox_workspace_write]", 1)[1].split("\n[", 1)[0]
        match = re.search(r"(?m)^writable_roots\s*=\s*(\[[^\n]*\])\s*$", section)
        if match:
            extra = json.loads(match[1])
            roots.update(
                os.path.normpath(p)
                for p in extra
                if isinstance(p, str) and os.path.isabs(p)
            )
    except (OSError, ValueError, IndexError):
        pass  # Other TOML spellings are outside this deliberately small reader.
    return roots


def clean_preview(options: list[str]) -> bool:
    """Git permits --no-dry-run; order matters and exclude values are operands."""
    dry_run, skip = False, False
    for option in options:
        if skip:
            skip = False
        elif option == "--":
            break
        elif option in {"-e", "--exclude"}:
            skip = True
        elif option == "--dry-run":
            dry_run = True
        elif option == "--no-dry-run":
            dry_run = False
        elif option == "--help":
            return True
        elif option.startswith("-") and not option.startswith("--"):
            # Short -e consumes the remaining letters as its exclude pattern.
            flags, exclude, pattern = option[1:].partition("e")
            if exclude and not pattern:
                skip = True
            if "h" in flags:
                return True
            if "n" in flags:
                dry_run = True
    return dry_run


def command_guard(command: str, roots: set[str], depth: int = 0) -> tuple[str, str]:
    try:
        commands = simple_commands(command)
    except ValueError:
        return (
            "",
            "Complex shell syntax is unclassified; normal authority/approval applies.",
        )
    advisory = ""
    for words in commands:
        words = unwrap(words)
        if not words:
            continue
        executable = Path(words[0]).name
        args = words[1:]
        shell_flags = next((a for a in args if a in {"-c", "-lc", "-ec", "-xc"}), None)
        if executable in {"sh", "bash", "zsh"} and shell_flags and depth < 2:
            position = args.index(shell_flags) + 1
            if position < len(args):
                blocked, note = command_guard(args[position], roots, depth + 1)
                if blocked:
                    return blocked, ""
                advisory = note or advisory
            continue
        git_args = git_arguments(words) if executable == "git" else []
        read_only = executable in {
            "echo",
            "printf",
            "rg",
            "grep",
            "cat",
            "head",
            "tail",
            "less",
            "wc",
        } or (git_args and git_args[0] in {"diff", "show", "log", "status", "grep"})
        if executable == "command" and args[:1] in (["-v"], ["-V"]):
            read_only = True
        if executable == "find" and not set(args).intersection(
            {
                "-exec",
                "-execdir",
                "-ok",
                "-okdir",
                "-delete",
                "-fprint",
                "-fprint0",
                "-fprintf",
                "-fls",
            }
        ):
            read_only = True
        # A remaining wrapper's -- is not the wrapped program's operand boundary.
        option_args = args
        if executable not in {"env", "command", "exec"} and "--" in args:
            option_args = args[: args.index("--")]
        if not read_only and any(
            a == "--owner-direct" or a.startswith("--owner-direct=")
            for a in option_args
        ):
            return "Agent execution cannot consume the human Owner Direct path.", ""
        if git_args:
            action, options = git_args[0], git_args[1:]
            # After --, even '-n'/'--hard' is a path, not an option.
            options = options[: options.index("--")] if "--" in options else options
            if action == "reset" and any(
                a == "--hard" or a.startswith("--hard=") for a in options
            ):
                return (
                    "Destructive git reset --hard is guarded; preserve existing work.",
                    "",
                )
            if action == "clean" and not clean_preview(git_args[1:]):
                return (
                    "Deleting git clean is guarded; use a dry run to inspect.",
                    "",
                )
            if action == "push":
                advisory = (
                    "git push is a remote write; resolve separate Owner "
                    "authority and approval."
                )
        if executable == "rm":
            options = args[: args.index("--")] if "--" in args else args
            recursive = any(
                a == "--recursive"
                or (
                    a.startswith("-")
                    and not a.startswith("--")
                    and ("r" in a or "R" in a)
                )
                for a in options
            )
            if recursive and any(
                os.path.isabs(a) and os.path.normpath(a) in roots for a in args
            ):
                return (
                    "Recursive deletion of repo/configured capability root is guarded.",
                    "",
                )
            if recursive:
                advisory = (
                    "Recursive deletion: hook cwd does not prove exec workdir; "
                    "inspect targets and authority."
                )
        remote = (
            (
                executable == "gh"
                and (
                    args[:2] == ["pr", "merge"]
                    or args[:2] in (["release", "create"], ["release", "upload"])
                )
            )
            or (
                executable in {"npm", "pnpm", "yarn", "cargo", "uv"}
                and "publish" in args
            )
            or (executable == "twine" and "upload" in args)
            or (executable == "docker" and args[:1] == ["push"])
            or (executable == "kubectl" and args[:1] in (["apply"], ["delete"]))
            or (
                executable == "vercel" and (not args or args[0] in {"deploy", "--prod"})
            )
        )
        if remote:
            advisory = (
                "Remote publication/merge/deployment requires separate Owner "
                "authority and approval."
            )
    return "", advisory


def verification_kind(command: str) -> str | None:
    try:
        commands = simple_commands(command)
    except ValueError:
        return None
    for words in commands:
        words = unwrap(words)
        if not words:
            continue
        executable, args = Path(words[0]).name, words[1:]
        if executable.startswith("python") and args[:1] == ["-m"]:
            executable, args = args[1] if len(args) > 1 else "", args[2:]
        if executable in {"pytest", "mypy"} or (
            executable == "ruff" and args[:1] == ["check"]
        ):
            return executable
        if executable in {"cpks", "cp_knowledge_tools.cli.cpks"} and (
            args[:2] == ["assurance", "verify"]
        ):
            return "cpks assurance verify"
    return None


def patch_paths(tool_input: dict[str, Any]) -> set[str]:
    result = set()
    for key in ("file_path", "path"):
        if isinstance(tool_input.get(key), str):
            result.add(tool_input[key])
    command = tool_input.get("command", "")
    if isinstance(command, str):
        result.update(
            re.findall(
                r"(?m)^\*\*\* (?:Update|Add|Delete|Move to)"
                r"(?: File)?: (.+)$",
                command,
            )
        )
    return result


def state_directory() -> Path:
    # Fixed OS temp root: no environment-variable bypass or repository state file.
    directory = Path("/tmp").resolve() / ("cpks-codex-hooks-" + str(os.getuid()))
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or (stat.S_IMODE(info.st_mode) != 0o700)
    ):
        raise ValueError("Unsafe session state directory")
    return directory


def load_state(path: Path, root: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(read_regular(path, MAX_JSON))
        if (
            not isinstance(value, dict)
            or value.get("schema") != 1
            or value.get("root") != str(root)
            or not isinstance(value.get("initial_dirty"), list)
            or not all(isinstance(p, str) for p in value["initial_dirty"])
            or not isinstance(value.get("files"), dict)
            or not all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in value["files"].items()
            )
            or not isinstance(value.get("generation"), int)
            or not isinstance(value.get("nudged_generation"), int)
        ):
            return None
        return value
    except (OSError, ValueError):
        return None


def save_state(path: Path, state: dict[str, Any]) -> None:
    data = json.dumps(state, sort_keys=True).encode()
    if len(data) > MAX_JSON:
        raise ValueError("Session state limit")
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".state-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def observe(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    event = payload["hook_event_name"]
    identity = payload.get("session_id")
    if not isinstance(identity, str) or not identity or len(identity) > 256:
        raise ValueError("Missing session identity")
    key = hashlib.sha256((identity + "\0" + str(root)).encode()).hexdigest()
    directory = state_directory()
    path = directory / (key + ".json")
    lock = os.open(
        directory / (key + ".lock"),
        os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
        0o600,
    )
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = load_state(path, root)
        current = snapshot(root)
        known = state is not None
        if state is None:
            state = {
                "schema": 1,
                "root": str(root),
                "initial_dirty": current["dirty"],
                "initial_head": current["head"],
                "initial_branch": current["branch"],
                "started": time.time(),
                "generation": 0,
                "nudged_generation": 0,
                "files": current["files"],
                "verification": None,
            }
        old = state["files"]
        changed = {
            p
            for p in old.keys() | current["files"].keys()
            if old.get(p) != current["files"].get(p)
        }
        notes = []
        if changed:
            state["generation"] += 1
            state["last_mutation"] = time.time()
            state["verification"] = None
            overlap = len(changed.intersection(state["initial_dirty"]))
            notes.append(
                f"Observed {len(changed)} content changes; {overlap} overlap "
                "initial dirty paths. Attribution/ownership is unknown."
            )
        state.update(
            files=current["files"],
            head=current["head"],
            branch=current["branch"],
            updated=time.time(),
        )
        if event == "SessionStart":
            notes.append(
                f"Repository {root}; branch {current['branch']}; HEAD "
                f"{current['head']}; {len(state['initial_dirty'])} initial dirty "
                "paths. Preserve existing work; resolve live rule homes and "
                "authority before material work. "
                + (
                    "Session baseline preserved."
                    if known
                    else "New/reconstructed baseline; prior evidence unknown."
                )
            )
        elif event == "PreToolUse":
            paths = patch_paths(payload.get("tool_input", {}))
            initial = set(state["initial_dirty"])
            if initial.intersection(paths) or (
                paths.intersection(str(root / p) for p in initial)
            ):
                notes.append(
                    "Edit overlaps initially dirty work; inspect and preserve it. "
                    "Ownership is not inferred; this is advisory only."
                )
        elif event == "PostToolUse":
            command = payload.get("tool_input", {}).get("command", "")
            kind = verification_kind(command) if isinstance(command, str) else None
            if kind:
                # 0.147 provides text only, not an authenticated exit status. Never
                # parse 'passed', JSON stdout or a claimed exit_code into success.
                state["verification"] = {
                    "kind": kind,
                    "outcome": "unknown",
                    "generation": state["generation"],
                }
                notes.append(
                    "Verification candidate observed; Codex 0.147 hook response "
                    "has no reliable exit status. Success remains unknown."
                )
        result: dict[str, Any] = {}
        if event == "Stop":
            if (
                payload.get("stop_hook_active") is False
                and state["generation"] > 0
                and state["nudged_generation"] != state["generation"]
            ):
                state["nudged_generation"] = state["generation"]
                result = {
                    "decision": "block",
                    "reason": "Changes were observed without hook-verifiable "
                    "success. Run or confirm the narrowest relevant verification; "
                    "report actual results. Codex 0.147 exposes no reliable exit "
                    "status to this hook. This reminder occurs once per mutation.",
                }
        elif notes:
            result = context(event, " ".join(notes))
        save_state(path, state)
        return result
    finally:
        os.close(lock)


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get("hook_event_name")
    if not isinstance(event, str) or event not in {
        "SessionStart",
        "PreToolUse",
        "PostToolUse",
        "Stop",
    }:
        return {}
    if event in {"PreToolUse", "PostToolUse"} and not isinstance(
        payload.get("tool_name"), str
    ):
        return context(event, "Malformed tool name; hook evidence unknown.")
    tool_input = payload.get("tool_input", {})
    if not isinstance(tool_input, dict):
        tool_input = {}
        payload = dict(payload, tool_input=tool_input)
    # Stateless denial remains effective even if state/cwd/Git is unavailable.
    if (
        event == "PreToolUse"
        and tool_input.get("authority_mode") == "human_owner_direct"
    ):
        return deny(
            "Agents cannot consume the explicit human Owner Direct runtime mode."
        )
    tool_name = payload.get("tool_name")
    local = isinstance(tool_name, str) and tool_name in LOCAL_TOOLS
    shell = isinstance(tool_name, str) and tool_name in {
        "Bash",
        "exec_command",
        "shell",
        "shell_command",
    }
    command = tool_input.get("command", "") if shell else ""
    advisory = ""
    if event == "PreToolUse" and isinstance(command, str):
        blocked, advisory = command_guard(command, {"/"})
        if blocked:
            return deny(blocked)
    if event in {"PreToolUse", "PostToolUse"} and not local:
        return {}
    try:
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not os.path.isabs(cwd):
            raise ValueError("Missing absolute cwd")
        root = Path(git(Path(cwd), "rev-parse", "--show-toplevel").strip()).resolve()
        if event == "PreToolUse" and isinstance(command, str):
            blocked, advisory = command_guard(command, protected_roots(root))
            if blocked:
                return deny(blocked)
        result = observe(payload, root)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RecursionError,
        subprocess.SubprocessError,
    ):
        result = (
            {}
            if event == "Stop"
            else context(
                str(event),
                "Hook session evidence unavailable/unknown; no authority or "
                "verification conclusion. Normal sandbox/approval still applies.",
            )
        )
    if advisory:
        output = result.setdefault("hookSpecificOutput", {"hookEventName": event})
        output["additionalContext"] = (
            output.get("additionalContext", "") + " " + advisory
        ).strip()
    return result


def main() -> None:
    try:
        raw = sys.stdin.buffer.read(MAX_JSON + 1)
        if len(raw) > MAX_JSON:
            raise ValueError("Input limit")
        payload = json.loads(raw)
        result = handle(payload) if isinstance(payload, dict) else {}
    except (ValueError, OSError, RecursionError):
        result = {}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
