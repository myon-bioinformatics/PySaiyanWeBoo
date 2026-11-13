"""Local repository-metadata v1 producer and advisory tooling versions (stdlib only).

``repo-metadata`` writes the identity record; ``tooling`` prints observed versions (reported, never pinned or
rejected). The probes sit under the historical ``canonical`` name so tests can patch shutil/subprocess.

Replaces the former vendored ``gh_identity.py repo-metadata --format v1``
invocation. Schema and JSON/JSONL identity path stay the Ironmate v1 contract.
"""
from __future__ import annotations

import argparse, json, os, platform, re, shutil, subprocess, sys
from datetime import datetime, timezone; from importlib import metadata as importlib_metadata; from pathlib import Path

REPOSITORY_METADATA_V1_SCHEMA = "1.0"
_RM_OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
_RM_NAME = re.compile(r"[A-Za-z0-9_.-]+")
_RM_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_RM_MEASUREMENTS = ("github_reported_size_bytes", "working_tree_bytes", "release_artifact_bytes")


class GitInspectionError(RuntimeError):
    """Local git inspection failed."""


def _rm_full_name(full_name: str) -> str:
    if not isinstance(full_name, str) or full_name.count("/") != 1:
        raise ValueError("repository must be owner/name")
    owner, name = full_name.split("/")
    if not _RM_OWNER.fullmatch(owner) or not _RM_NAME.fullmatch(name) or name in (".", ".."):
        raise ValueError("repository must be owner/name")
    return full_name


def _rm_sha(value: str, name: str = "sha") -> str:
    if not isinstance(value, str) or not _RM_SHA.fullmatch(value.lower()):
        raise ValueError(name + " must be a full 40- or 64-hex commit SHA")
    return value.lower()


def _rm_time(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(name + " must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(name + " must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(name + " must include a timezone")
    return value


def _git(root: str | Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "--no-pager", "-c", "i18n.logOutputEncoding=UTF-8", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except FileNotFoundError as error:
        raise GitInspectionError("git executable not found") from error
    except (OSError, subprocess.SubprocessError) as error:
        raise GitInspectionError(type(error).__name__) from error
    if result.returncode != 0:
        raise GitInspectionError("git exited with status " + str(result.returncode))
    return result.stdout.strip()


def checkout_head(root: str | Path = ".") -> dict[str, object]:
    """The commit actually checked out at root (never GITHUB_SHA or other env)."""
    sha = _rm_sha(_git(root, "rev-parse", "--verify", "HEAD^{commit}"), "HEAD")
    fields = _git(root, "show", "-s", "--format=%cI%x1f%s", "HEAD").split("\x1f", 1)
    if len(fields) != 2 or not fields[1]:
        raise GitInspectionError("HEAD has no committer date or subject")
    branch = _git(root, "branch", "--show-current") or None
    return {
        "sha": sha,
        "branch": branch,
        "detached": branch is None,
        "timestamp": _rm_time(fields[0], "timestamp"),
        "subject": fields[1].splitlines()[0],
    }


def validate_repository_metadata_v1(record: dict) -> dict:
    if not isinstance(record, dict) or set(record) != {
        "schema_version",
        "repository",
        "head",
        "measurements",
        "tooling",
        "generated_at",
    }:
        raise ValueError("unexpected or missing top-level fields")
    if record["schema_version"] != REPOSITORY_METADATA_V1_SCHEMA:
        raise ValueError("unsupported schema_version")
    head = record["head"]
    if not isinstance(head, dict) or set(head) != {"sha", "short_sha", "branch", "timestamp", "subject"}:
        raise ValueError("invalid head")
    if not isinstance(head["sha"], str) or not _RM_SHA.fullmatch(head["sha"]):
        raise ValueError("sha must be lowercase full hex")
    if head["short_sha"] != head["sha"][:8]:
        raise ValueError("short_sha must be the first 8 characters of sha")
    if not head["branch"] or not head["subject"]:
        raise ValueError("branch and subject are required")
    _rm_time(head["timestamp"], "timestamp")
    _rm_time(record["generated_at"], "generated_at")
    if not isinstance(record["repository"], dict) or set(record["repository"]) != {"full_name"}:
        raise ValueError("invalid repository")
    _rm_full_name(record["repository"]["full_name"])
    sizes = record["measurements"]
    if not isinstance(sizes, dict) or set(sizes) != set(_RM_MEASUREMENTS) or any(
        value is not None and (type(value) is not int or value < 0) for value in sizes.values()
    ):
        raise ValueError("measurements must be non-negative integers or null")
    tooling = record["tooling"]
    if not isinstance(tooling, dict):
        raise ValueError("tooling values must be short version labels")
    return record


def repository_metadata_v1(
    root: str | Path = ".",
    *,
    repository: str,
    env=None,
    expected_sha: str | None = None,
    generated_at: str | None = None,
    tooling=None,
    measurements=None,
) -> dict:
    env = os.environ if env is None else env
    head = checkout_head(root)
    if expected_sha is not None and head["sha"] != _rm_sha(expected_sha, "expected_sha"):
        raise ValueError("checkout HEAD does not match expected_sha")
    branch = (
        (env.get("GITHUB_HEAD_REF") or "").strip()
        or (env.get("GITHUB_REF_NAME") or "").strip()
        or head["branch"]
        or "detached"
    )
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    sizes = dict.fromkeys(_RM_MEASUREMENTS)
    extra = set(measurements or {}) - set(_RM_MEASUREMENTS)
    if extra:
        raise ValueError("unknown measurements: " + ", ".join(sorted(extra)))
    sizes.update(measurements or {})
    return validate_repository_metadata_v1(
        {
            "schema_version": REPOSITORY_METADATA_V1_SCHEMA,
            "repository": {"full_name": _rm_full_name(repository)},
            "head": {
                "sha": head["sha"],
                "short_sha": head["sha"][:8],
                "branch": branch,
                "timestamp": head["timestamp"],
                "subject": head["subject"],
            },
            "measurements": sizes,
            "tooling": dict(tooling or {}),
            "generated_at": _rm_time(generated_at or now, "generated_at"),
        }
    )


def write_repository_metadata(record: dict, output_dir: str | Path) -> dict[str, str]:
    validate_repository_metadata_v1(record)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    pretty = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    (output / "repository-metadata.json").write_text(pretty, encoding="utf-8")
    (output / "repository-metadata.jsonl").write_text(line, encoding="utf-8")
    return {"json": "repository-metadata.json", "jsonl": "repository-metadata.jsonl"}


# --- 🧰 tooling versions (was tools/web_ui_tooling_meta.py) ---

RUNTIME_KEYS = ("python",)
COMMANDS = ("git", "gh", "node", "npx")
DISTRIBUTIONS = (("pytest", "pytest"), ("stagehand", "stagehand"))
_PACKAGE_VERSION = re.compile(
    r"(?:[0-9]+!)?[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?(?:\.dev[0-9]+)?"
    r"(?:\+(?:[0-9A-Za-z][0-9A-Za-z.-]*)?)?"
)
_TOOL_ARGS = {
    "git": "--version",
    "gh": "--version",
    "node": "--version",
    "npm": "--version",
    "npx": "--version",
}
_VERSION = r"[0-9]+(?:\.[0-9]+)+(?:[-+._][0-9A-Za-z][0-9A-Za-z.-]*)?"
_TOOL_PATTERNS = {
    "git": re.compile(r"git version (?P<v>" + _VERSION + r")(?:\s.*)?"),
    "gh": re.compile(r"gh version (?P<v>" + _VERSION + r")(?:\s.*)?"),
    "node": re.compile(r"v(?P<v>" + _VERSION + r")"),
    "npm": re.compile(r"(?P<v>" + _VERSION + r")"),
    "npx": re.compile(r"(?P<v>" + _VERSION + r")"),
    "python": re.compile(
        r"(?P<v>(?:[0-9]+!)?[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?"
        r"(?:\.dev[0-9]+)?(?:\+(?:[0-9A-Za-z][0-9A-Za-z.-]*)?)?)"
    ),
}


def tool_versions(commands=(), *, include_python=False, timeout=5.0):
    """Explicitly requested, allowlisted tool versions; missing tools are omitted."""
    if isinstance(commands, (str, bytes)):
        raise TypeError("commands must be a sequence of command names")
    unknown = [command for command in commands if command not in _TOOL_ARGS]
    if unknown:
        raise ValueError("unsupported tooling command: " + ", ".join(map(str, unknown)))
    observed = {}
    if include_python:
        match = _TOOL_PATTERNS["python"].fullmatch(platform.python_version())
        if match:
            observed["python"] = match.group("v")
    for command in commands:
        executable = shutil.which(command)
        if not executable:
            continue
        try:
            result = subprocess.run(
                [executable, _TOOL_ARGS[command]],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        text = (result.stdout.strip() or result.stderr.strip()) if result.returncode == 0 else ""
        first = next((line.strip() for line in text.splitlines() if line.strip()), "")
        match = _TOOL_PATTERNS[command].fullmatch(first)
        if match and len(match.group("v")) <= 32:
            observed[command] = match.group("v")
    return observed


# Historical alias: tests patch canonical.shutil / canonical.subprocess /
# canonical.tool_versions the same way they patched the old vendored module.
canonical = sys.modules[__name__]


def observe_package_version(distribution: str) -> str | None:
    try:
        value = importlib_metadata.version(distribution)
    except importlib_metadata.PackageNotFoundError:
        return None
    candidate = value.strip()
    match = _PACKAGE_VERSION.fullmatch(candidate)
    if not match or len(match.group(0)) > 32:
        return None
    return match.group(0)


def collect() -> dict[str, object]:
    owners = list(RUNTIME_KEYS) + list(COMMANDS) + [key for key, _ in DISTRIBUTIONS]
    if len(owners) != len(set(owners)):
        raise ValueError("tooling keys must have exactly one canonical source")
    observed = canonical.tool_versions(COMMANDS, include_python=True)
    for key, distribution in DISTRIBUTIONS:
        value = observe_package_version(distribution)
        if value is not None:
            observed[key] = value
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": {key: observed[key] for key in RUNTIME_KEYS if key in observed},
        "commands": {key: observed[key] for key in COMMANDS if key in observed},
        "packages": {key: observed[key] for key, _ in DISTRIBUTIONS if key in observed},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit repository-metadata v1 JSON/JSONL, or the observed tooling versions")
    parser.add_argument("cmd", choices=("repo-metadata", "tooling"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--format", choices=("v1",), default="v1")
    parser.add_argument("--expected-sha")
    parser.add_argument("--generated-at")
    parser.add_argument("--output-dir")
    ns = parser.parse_args(argv)
    if ns.cmd == "tooling":
        print(json.dumps(collect(), indent=2, ensure_ascii=False))
        return 0
    if ns.format != "v1":  # pragma: no cover - argparse choices already enforce
        raise SystemExit("only --format v1 is supported")
    if not ns.repository:
        raise SystemExit("--repository or GITHUB_REPOSITORY required")
    record = repository_metadata_v1(
        ns.root,
        repository=ns.repository,
        expected_sha=ns.expected_sha,
        generated_at=ns.generated_at,
    )
    if ns.output_dir:
        write_repository_metadata(record, ns.output_dir)
    else:
        print(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess CLI
    raise SystemExit(main())
