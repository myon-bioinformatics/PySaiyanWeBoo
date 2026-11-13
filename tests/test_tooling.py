"""🧰 Tooling: repository metadata, CI and JUnit contracts, Node launch, the diagnostics page, the single file and the vendor locks."""
from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple, Union

import pytest
import yaml

import pysaiyanweboo
import pysaiyanweboo as ui
from support import node_js
from tools import repository_metadata as rm
from tools.repository_metadata import collect

ROOT = Path(__file__).resolve().parents[1]


# ═══ 🧰 tooling ═══════════════════════════════════════════════════════════════════════════════════════════

def test_required_github_tooling_is_visible():
    assert shutil.which("git")
    assert shutil.which("gh")


def test_canonical_repository_metadata_and_separate_tooling(tmp_path, monkeypatch):
    # Use a real isolated checkout to prove the producer -> JSON/JSONL -> JS path.
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(checkout)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "--allow-empty", "-m", "metadata <script>fixture</script>"],
        cwd=checkout, check=True, capture_output=True,
    )
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout, text=True).strip()
    env = {**os.environ, "GITHUB_SHA": "f" * 40, "GITHUB_HEAD_REF": "topic/canonical",
           "GITHUB_REF_NAME": "123/merge"}
    output = tmp_path / "metadata"
    subprocess.run(
        [sys.executable, "-S", str(ROOT / "tools/repository_metadata.py"), "repo-metadata",
         "--format", "v1", "--repository", "myon-bioinformatics/PySaiyanWeBoo", "--root", str(checkout),
         "--output-dir", str(output)],
        check=True, env=env, capture_output=True, text=True,
    )
    record_path = output / "repository-metadata.json"
    record = json.loads(record_path.read_text())
    assert record == json.loads((output / "repository-metadata.jsonl").read_text())
    assert record["repository"] == {"full_name": "myon-bioinformatics/PySaiyanWeBoo"}
    assert record["head"]["sha"] == sha
    assert record["head"]["short_sha"] == sha[:8]
    assert record["head"]["branch"] == "topic/canonical"
    assert all(value is None for value in record["measurements"].values())
    # The browser renderer on that record: the commit line as the producer wrote it, three unmeasured sizes, the subject escaped.
    shown = json.loads(node_js("const r=require('./js/repository-diagnostics.js'),c=JSON.parse(require('fs').readFileSync(process.argv[2],'utf8'));"
                               "console.log(JSON.stringify({line:r.commitLine(c),html:r.render(c)}))", str(record_path)).stdout)
    head = record["head"]
    assert shown["line"] == f"Commit {head['short_sha']} · {head['branch']} · {head['timestamp']} · {head['subject']}"
    assert record["repository"]["full_name"] in shown["html"] and shown["html"].count("not measured") == 3
    assert "<script>" not in shown["html"] and "&lt;script&gt;fixture&lt;/script&gt;" in shown["html"]

    # Advisory collection reports tooling versions only; never head/branch identity.
    def fake_tool_versions(commands, *, include_python=False, **_):
        observed = {command: "1.2.3" for command in commands}
        if include_python:
            observed["python"] = "1.2.3"
        return observed
    monkeypatch.setattr(rm.canonical, "tool_versions", fake_tool_versions)
    monkeypatch.setattr(rm, "observe_package_version", lambda _: "4.1.0")
    metadata = collect()
    assert set(metadata) == {"generated_at_utc", "runtime", "commands", "packages"}
    assert metadata["runtime"]["python"]
    assert set(metadata["packages"]) == {"pytest", "stagehand"}


def test_stagehand_v4_python_surface():
    stagehand = pytest.importorskip("stagehand")
    assert hasattr(stagehand, "Stagehand") or hasattr(stagehand, "AsyncStagehand")


# ═══ 🧳 portable tooling ══════════════════════════════════════════════════════════════════════════════════
# Consumer projection, canonical ownership, and standalone JSON regressions.

canonical = rm.canonical


@pytest.mark.parametrize("partial", [False, True])
def test_partial_or_empty_tooling_omits_unavailable_keys(monkeypatch, partial):
    monkeypatch.setattr(platform, "python_version", lambda: "3.12.8" if partial else "invalid")
    probes = []

    def run(argv, **kwargs):
        probes.append(argv)
        assert kwargs.get("shell") is not True
        assert kwargs["timeout"] == 5.0
        assert argv[1:] == ["--version"]
        return SimpleNamespace(returncode=0, stdout="git version 2.45.1\n", stderr="")

    monkeypatch.setattr(canonical.shutil, "which", lambda name: "git-fixture" if partial and name == "git" else None)
    monkeypatch.setattr(canonical.subprocess, "run", run)

    def package(name):
        if partial and name == "pytest":
            return "9.0.0"
        raise rm.importlib_metadata.PackageNotFoundError(name)

    monkeypatch.setattr(rm.importlib_metadata, "version", package)
    result = rm.collect()
    assert set(result) == {"generated_at_utc", "runtime", "commands", "packages"}
    assert result["runtime"] == ({"python": "3.12.8"} if partial else {})
    assert result["commands"] == ({"git": "2.45.1"} if partial else {})
    assert result["packages"] == ({"pytest": "9.0.0"} if partial else {})
    assert probes == ([["git-fixture", "--version"]] if partial else [])
    assert json.loads(json.dumps(result)) == result
    assert all(isinstance(v, str) and v != "unknown" for group in ("runtime", "commands", "packages") for v in result[group].values())


def test_consumer_only_requests_allowlisted_observations(monkeypatch):
    calls = []

    def tool_versions(commands, *, include_python=False, **kwargs):
        calls.append({"commands": commands, "include_python": include_python})
        observed = {command: "1.0.0" for command in commands}
        if include_python:
            observed["python"] = "3.12.8"
        return observed

    monkeypatch.setattr(canonical, "tool_versions", tool_versions)
    monkeypatch.setattr(rm, "observe_package_version", lambda name: {"pytest": "9.0.0", "stagehand": "4.1.0"}[name])
    result = rm.collect()
    assert calls == [{"commands": rm.COMMANDS, "include_python": True}]
    assert result["runtime"] == {"python": "3.12.8"}
    assert result["commands"] == {"git": "1.0.0", "gh": "1.0.0", "node": "1.0.0", "npx": "1.0.0"}
    assert result["packages"] == {"pytest": "9.0.0", "stagehand": "4.1.0"}


@pytest.mark.parametrize("collision", ["runtime", "command", "package", "duplicate-command"])
def test_duplicate_canonical_owners_fail_before_probing(monkeypatch, collision):
    def unexpected(*args, **kwargs):
        pytest.fail("collision must fail before observations")

    monkeypatch.setattr(canonical, "tool_versions", unexpected)
    monkeypatch.setattr(rm, "observe_package_version", unexpected)
    if collision == "duplicate-command":
        monkeypatch.setattr(rm, "COMMANDS", ("git", "git"))
    elif collision == "runtime":
        monkeypatch.setattr(rm, "DISTRIBUTIONS", rm.DISTRIBUTIONS + (("python", "other"),))
    elif collision == "command":
        monkeypatch.setattr(rm, "DISTRIBUTIONS", rm.DISTRIBUTIONS + (("git", "other"),))
    else:
        monkeypatch.setattr(rm, "DISTRIBUTIONS", rm.DISTRIBUTIONS + (("pytest", "other"),))
    with pytest.raises(ValueError, match="exactly one canonical source"):
        rm.collect()


def test_standalone_json_is_stdlib_only_and_does_not_need_checkout(tmp_path):
    env = {**os.environ, "PATH": str(tmp_path), "PYTHONPATH": ""}
    result = subprocess.run([sys.executable, "-S", str(ROOT / "tools/repository_metadata.py"), "tooling"],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    record = json.loads(result.stdout)
    assert set(record) == {"generated_at_utc", "runtime", "commands", "packages"}
    assert record["runtime"] == {"python": platform.python_version()}
    assert record["commands"] == {}
    assert record["packages"] == {}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("failure", ["nonzero", "malformed", "timeout", "oserror"])
def test_failed_canonical_observations_are_omitted(monkeypatch, failure):
    monkeypatch.setattr(platform, "python_version", lambda: "3.12.8")
    monkeypatch.setattr(canonical.shutil, "which", lambda name: name)

    def run(argv, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        if failure == "oserror":
            raise OSError("private path must not escape")
        return SimpleNamespace(returncode=1 if failure == "nonzero" else 0,
                               stdout="private malformed output" if failure == "malformed" else "git version 2.45.1",
                               stderr="")

    monkeypatch.setattr(canonical.subprocess, "run", run)
    monkeypatch.setattr(rm.importlib_metadata, "version", lambda _: "private malformed package")
    first = rm.collect()
    second = rm.collect()
    for record in (first, second):
        assert record["runtime"] == {"python": "3.12.8"}
        assert record["commands"] == record["packages"] == {}
        del record["generated_at_utc"]
    assert json.dumps(first) == json.dumps(second)


def test_tool_versions_rejects_bad_commands():
    with pytest.raises(TypeError, match="sequence of command names"):
        rm.tool_versions("git")
    with pytest.raises(TypeError, match="sequence of command names"):
        rm.tool_versions(b"git")
    with pytest.raises(ValueError, match="unsupported tooling command"):
        rm.tool_versions(("git", "nope"))


def test_tool_versions_without_python_skips_runtime(monkeypatch):
    monkeypatch.setattr(rm.shutil, "which", lambda _: None)
    assert rm.tool_versions(("git",), include_python=False) == {}


# ═══ 🏷️ repository metadata ══════════════════════════════════════════════════════════════════════════════
# Local repository-metadata v1 producer regressions (no gh_identity).

def _init_checkout(path: Path, message: str = "fixture subject") -> str:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            message,
        ],
        cwd=path,
        check=True,
        capture_output=True,
    )
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


def test_repository_metadata_v1_roundtrip_and_cli(tmp_path):
    checkout = tmp_path / "checkout"
    sha = _init_checkout(checkout, "metadata <script>fixture</script>")
    env = {
        **os.environ,
        "GITHUB_SHA": "f" * 40,
        "GITHUB_HEAD_REF": "topic/local",
        "GITHUB_REF_NAME": "123/merge",
    }
    record = rm.repository_metadata_v1(
        checkout,
        repository="myon-bioinformatics/PySaiyanWeBoo",
        env=env,
    )
    assert record["repository"] == {"full_name": "myon-bioinformatics/PySaiyanWeBoo"}
    assert record["head"]["sha"] == sha
    assert record["head"]["short_sha"] == sha[:8]
    assert record["head"]["branch"] == "topic/local"
    assert all(value is None for value in record["measurements"].values())
    assert record["tooling"] == {}

    out = tmp_path / "out"
    written = rm.write_repository_metadata(record, out)
    assert written == {"json": "repository-metadata.json", "jsonl": "repository-metadata.jsonl"}
    pretty = json.loads((out / "repository-metadata.json").read_text(encoding="utf-8"))
    line = json.loads((out / "repository-metadata.jsonl").read_text(encoding="utf-8"))
    assert pretty == line == record

    cli_out = tmp_path / "cli"
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(ROOT / "tools/repository_metadata.py"),
            "repo-metadata",
            "--format",
            "v1",
            "--repository",
            "myon-bioinformatics/PySaiyanWeBoo",
            "--root",
            str(checkout),
            "--output-dir",
            str(cli_out),
        ],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert json.loads((cli_out / "repository-metadata.json").read_text(encoding="utf-8"))["head"]["sha"] == sha


def test_repository_metadata_v1_rejects_bad_inputs(tmp_path):
    checkout = tmp_path / "checkout"
    sha = _init_checkout(checkout)
    with pytest.raises(ValueError, match="owner/name"):
        rm.repository_metadata_v1(checkout, repository="not-a-repo")
    with pytest.raises(ValueError, match="expected_sha"):
        rm.repository_metadata_v1(
            checkout,
            repository="myon-bioinformatics/PySaiyanWeBoo",
            expected_sha="0" * 40,
        )
    with pytest.raises(ValueError, match="unknown measurements"):
        rm.repository_metadata_v1(
            checkout,
            repository="myon-bioinformatics/PySaiyanWeBoo",
            measurements={"nope": 1},
        )
    with pytest.raises(ValueError, match="must be a full"):
        rm._rm_sha("deadbeef", "x")
    with pytest.raises(ValueError, match="timezone"):
        rm._rm_time("2026-01-01T00:00:00", "t")
    with pytest.raises(ValueError, match="ISO 8601"):
        rm._rm_time(123, "t")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="ISO 8601"):
        rm._rm_time("not-a-time", "t")
    bad = {
        "schema_version": "9.9",
        "repository": {"full_name": "myon-bioinformatics/PySaiyanWeBoo"},
        "head": {
            "sha": sha,
            "short_sha": sha[:8],
            "branch": "main",
            "timestamp": "2026-01-01T00:00:00Z",
            "subject": "x",
        },
        "measurements": dict.fromkeys(rm._RM_MEASUREMENTS),
        "tooling": {},
        "generated_at": "2026-01-01T00:00:00Z",
    }
    with pytest.raises(ValueError, match="unsupported schema_version"):
        rm.validate_repository_metadata_v1(bad)
    with pytest.raises(ValueError, match="unexpected or missing"):
        rm.validate_repository_metadata_v1({"schema_version": "1.0"})
    bad_head = dict(bad)
    bad_head["schema_version"] = "1.0"
    bad_head["head"] = dict(bad["head"], short_sha="ffffffff")
    with pytest.raises(ValueError, match="short_sha"):
        rm.validate_repository_metadata_v1(bad_head)
    empty_branch = dict(bad)
    empty_branch["schema_version"] = "1.0"
    empty_branch["head"] = dict(bad["head"], branch="")
    with pytest.raises(ValueError, match="branch and subject"):
        rm.validate_repository_metadata_v1(empty_branch)
    bad_sizes = dict(bad)
    bad_sizes["schema_version"] = "1.0"
    bad_sizes["measurements"] = dict.fromkeys(rm._RM_MEASUREMENTS, -1)
    with pytest.raises(ValueError, match="measurements"):
        rm.validate_repository_metadata_v1(bad_sizes)
    bad_tooling = dict(bad)
    bad_tooling["schema_version"] = "1.0"
    bad_tooling["tooling"] = []  # type: ignore[assignment]
    with pytest.raises(ValueError, match="tooling"):
        rm.validate_repository_metadata_v1(bad_tooling)
    bad_repo = dict(bad)
    bad_repo["schema_version"] = "1.0"
    bad_repo["repository"] = {"full_name": "myon-bioinformatics/PySaiyanWeBoo", "extra": 1}
    with pytest.raises(ValueError, match="invalid repository"):
        rm.validate_repository_metadata_v1(bad_repo)
    with pytest.raises(ValueError, match="owner/name"):
        rm._rm_full_name("myon-bioinformatics/..")


def test_git_inspection_errors(tmp_path, monkeypatch):
    with pytest.raises(rm.GitInspectionError, match="git executable not found"):
        def boom(*args, **kwargs):
            raise FileNotFoundError("git")

        monkeypatch.setattr(rm.subprocess, "run", boom)
        rm._git(tmp_path, "status")

    def os_boom(*args, **kwargs):
        raise OSError("denied")

    monkeypatch.setattr(rm.subprocess, "run", os_boom)
    with pytest.raises(rm.GitInspectionError, match="OSError"):
        rm._git(tmp_path, "status")

    def bad_status(*args, **kwargs):
        return type("R", (), {"returncode": 128, "stdout": "", "stderr": "fail"})()

    monkeypatch.setattr(rm.subprocess, "run", bad_status)
    with pytest.raises(rm.GitInspectionError, match="exited with status"):
        rm._git(tmp_path, "status")


def test_main_prints_without_output_dir(tmp_path, capsys, monkeypatch):
    checkout = tmp_path / "checkout"
    _init_checkout(checkout)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        rm.main(["repo-metadata", "--root", str(checkout)])
    assert "repository" in str(excinfo.value)
    code = rm.main(
        [
            "repo-metadata",
            "--format",
            "v1",
            "--repository",
            "myon-bioinformatics/PySaiyanWeBoo",
            "--root",
            str(checkout),
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1.0"


def test_detached_branch_label(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    sha = _init_checkout(checkout)
    subprocess.run(["git", "checkout", "--detach", "HEAD"], cwd=checkout, check=True, capture_output=True)
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    record = rm.repository_metadata_v1(
        checkout,
        repository="myon-bioinformatics/PySaiyanWeBoo",
        env={},
    )
    assert record["head"]["branch"] == "detached"
    assert record["head"]["sha"] == sha


def test_validate_invalid_head_and_sha(tmp_path):
    checkout = tmp_path / "checkout"
    sha = _init_checkout(checkout)
    base = rm.repository_metadata_v1(
        checkout, repository="myon-bioinformatics/PySaiyanWeBoo", env={}
    )
    bad = dict(base)
    bad["head"] = {"sha": sha}
    with pytest.raises(ValueError, match="invalid head"):
        rm.validate_repository_metadata_v1(bad)
    bad2 = dict(base)
    bad2["head"] = dict(base["head"], sha=sha.upper())
    with pytest.raises(ValueError, match="lowercase full hex"):
        rm.validate_repository_metadata_v1(bad2)


def test_checkout_head_rejects_empty_subject(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    _init_checkout(checkout)

    def fake_git(root, *args):
        if args[:2] == ("rev-parse", "--verify"):
            return "a" * 40
        if args[0] == "show":
            return "2026-01-01T00:00:00+00:00\x1f"
        if args[:2] == ("branch", "--show-current"):
            return "main"
        raise AssertionError(args)

    monkeypatch.setattr(rm, "_git", fake_git)
    with pytest.raises(rm.GitInspectionError, match="no committer date or subject"):
        rm.checkout_head(checkout)


def test_main_with_output_dir(tmp_path):
    checkout = tmp_path / "checkout"
    _init_checkout(checkout)
    out = tmp_path / "meta"
    code = rm.main(
        [
            "repo-metadata",
            "--repository",
            "myon-bioinformatics/PySaiyanWeBoo",
            "--root",
            str(checkout),
            "--output-dir",
            str(out),
            "--expected-sha",
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout, text=True).strip(),
            "--generated-at",
            "2026-01-01T00:00:00Z",
        ]
    )
    assert code == 0
    assert (out / "repository-metadata.json").is_file()


def test_module_main_entrypoint(tmp_path):
    checkout = tmp_path / "checkout"
    _init_checkout(checkout)
    result = subprocess.run(
        [sys.executable, "-m", "tools.repository_metadata", "repo-metadata",
         "--repository", "myon-bioinformatics/PySaiyanWeBoo",
         "--root", str(checkout)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    # -m tools.repository_metadata may fail if tools is not a package; allow script path
    if result.returncode != 0:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/repository_metadata.py"), "repo-metadata",
             "--repository", "myon-bioinformatics/PySaiyanWeBoo",
             "--root", str(checkout)],
            capture_output=True,
            text=True,
            check=True,
        )
    assert "schema_version" in result.stdout


# ═══ 📍 parent workflow pins ══════════════════════════════════════════════════════════════════════════════
# Local rollout contract; adopted vendor locks are deliberately independent.

PARENT = "myon-bioinformatics/myon-bioinformatics"


def test_parent_workflow_references_use_reviewed_rollout_commit():
    parent_workflow_pin = "9e3da7ae1846e9604ebc24bb5178f7de094a4e77"
    pins = []
    for path in sorted((ROOT / ".github/workflows").glob("*")):
        if path.suffix not in (".yml", ".yaml"):
            continue
        text = path.read_text(encoding="utf-8")
        # Capture mutable and shortened references too, rather than ignoring them.
        pins.extend(re.findall(r"uses:\s*['\"]?" + re.escape(PARENT) + r"/[^\s@'\"]+@([^\s'\"]+)", text))
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.fullmatch(r"\s+repository:\s*['\"]?" + re.escape(PARENT) + r"['\"]?\s*", line):
                refs = [re.fullmatch(r"\s+ref:\s*['\"]?([^\s'\"]+)['\"]?\s*", item) for item in lines[i + 1:i + 12]]
                if not any(re.fullmatch(r"\s+path:\s*['\"]?\.vendor-sync-tools['\"]?\s*", item) for item in lines[i + 1:i + 12]):
                    pins.append(next((m.group(1) for m in refs if m), None))
    assert pins, "shared parent references must remain observable"
    assert set(pins) == {parent_workflow_pin}, pins


# ═══ 🧪 junit evidence ════════════════════════════════════════════════════════════════════════════════════
# Keep tooling probe failures red while exporting compact failure identities.

def test_tooling_probe_child_keeps_exit_status_with_junit(tmp_path):
    importer = ROOT / ".junit-tools" / "xprobe.py"
    if not importer.is_file() and os.environ.get("GITHUB_ACTIONS") != "true":
        pytest.skip("optional local JUnit regression: fetch the pinned importer (docs/junit-evidence.md)")
    assert importer.is_file(), "CI must provision the pinned test-only JUnit importer"
    evidence = ROOT / "build" / "controlled-failure"  # ci.yml uploads this folder as junit-controlled-python-3.15
    evidence.mkdir(parents=True, exist_ok=True)
    fixture = tmp_path / "test_probe.py"
    fixture.write_text('''
import pytest
from tools.repository_metadata import canonical

@pytest.fixture
def unavailable(monkeypatch):
    monkeypatch.setattr(canonical.shutil, "which", lambda _: None)

def test_unavailable_command(unavailable):
    assert canonical.tool_versions(("git",), include_python=False) == {}

@pytest.mark.parametrize("command", ["PARAMETER_SENTINEL"], ids=["PARAMETER_SENTINEL"])
def test_wrong_probe_expectation(unavailable, command):
    print("STDOUT_SENTINEL")
    assert canonical.tool_versions(("git",), include_python=False) == "ASSERTION_SENTINEL", command

@pytest.fixture
def broken_setup():
    raise RuntimeError("SETUP_SENTINEL")

def test_probe_setup_error(broken_setup):
    pass

def test_skip():
    pytest.skip("synthetic skipped probe")
''', encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTEST_ADDOPTS="")
    command = ["uv", "run", "pytest", str(fixture), "-c", os.devnull,
               "--rootdir", str(tmp_path), "--confcutdir", str(tmp_path), "-q"]
    plain = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    reported = subprocess.run(command + ["--junitxml", str(evidence / "junit.xml"),
                              "-o", "junit_logging=all"], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=60)
    (evidence / "exit.json").write_text(json.dumps({"without_junit": plain.returncode,
                                                "with_junit": reported.returncode}), encoding="utf-8")
    assert plain.returncode == reported.returncode == 1, plain.stdout + plain.stderr + reported.stdout + reported.stderr
    data = importer.read_bytes()
    assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == "dbc5b7d55005d6288c072a7612584d6170c216f4"
    spec = importlib.util.spec_from_file_location("probe_junit_xprobe", importer)
    xprobe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(xprobe)
    raw = (evidence / "junit.xml").read_text(encoding="utf-8")
    imported = xprobe.cases_from_junit(raw, repository="myon-bioinformatics/PySaiyanWeBoo", report_id="controlled-probe")
    assert imported["truncated"] is False
    cases = imported["cases"]
    assert {(c["value"]["test"], c["value"]["kind"]) for c in cases} == {
        ("test_wrong_probe_expectation", "failure"), ("test_probe_setup_error", "error")}
    compact = xprobe.corpus_to_json(cases, jsonl=True)
    (evidence / "failure-identity.jsonl").write_text(compact, encoding="utf-8")
    assert all(c["context"]["commit_sha"] is None for c in cases)
    for sentinel in ("PARAMETER_SENTINEL", "STDOUT_SENTINEL", "ASSERTION_SENTINEL", "SETUP_SENTINEL"):
        assert sentinel in raw and sentinel not in compact


# ═══ 🧪 junit workflow contract ═══════════════════════════════════════════════════════════════════════════
# Guard the real workflow's failure/evidence contract, using test-only PyYAML.

CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
COMMAND = "uv run --group stagehand pytest -v --junitxml=build/test-results/pytest-3.15.xml"


def _step(job, name):
    matches = [step for step in job["steps"] if step.get("name") == name]
    assert len(matches) == 1, name
    return matches[0]


def _upload(job, name):
    matches = [step for step in job["steps"]
               if step.get("uses", "").startswith("actions/upload-artifact@")
               and step.get("with", {}).get("name") == name]
    assert len(matches) == 1, name
    return matches[0]


def _assert_contract(workflow):
    producer = workflow["jobs"]["tooling"]
    run = _step(producer, "Run pytest")
    assert producer.get("continue-on-error", False) is False
    assert run.get("continue-on-error", False) is False
    assert run.get("if") is None
    # The exact normalized command rejects || true, set +e and trailing exit 0.
    assert " ".join(run["run"].split()) == COMMAND
    assert "env" not in run  # the test writes build/controlled-failure itself
    for name, path in (
        ("junit-python-3.15", "build/test-results/pytest-3.15.xml"),
        ("junit-controlled-python-3.15", "build/controlled-failure/"),
    ):
        upload = _upload(producer, name)
        assert producer["steps"].index(run) < producer["steps"].index(upload)
        assert upload.get("if") == "always()"
        assert upload.get("continue-on-error", False) is False
        assert upload["with"]["path"].strip() == path
        assert upload["with"]["if-no-files-found"] == "error"
        assert upload["with"]["retention-days"] == 14
    collector = workflow["jobs"]["failure-identity"]
    assert collector["needs"] == ["changes", "tooling"]
    assert collector["if"] == "(always()) && needs.changes.outputs.product_changed == 'true'"
    assert collector.get("continue-on-error", False) is False
    assert collector["uses"] == ("myon-bioinformatics/myon-bioinformatics/.github/workflows/"
                                 "reusable-junit-identity.yml@9e3da7ae1846e9604ebc24bb5178f7de094a4e77")
    reports = json.loads(collector["with"]["expected-reports"])
    assert isinstance(reports, list) and len(reports) == 2
    assert set(reports) == {
        "junit-python-3.15/pytest-3.15.xml",
        "junit-controlled-python-3.15/junit.xml",
    }


def test_failure_evidence_workflow_contract():
    _assert_contract(yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8")))


def test_failure_evidence_contract_rejects_unsafe_mutations():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    _assert_contract(workflow)  # A broken baseline must not make all mutants pass.
    producer = workflow["jobs"]["tooling"]
    run_index = producer["steps"].index(_step(producer, "Run pytest"))
    job_path = ("jobs", "tooling")
    run_path = job_path + ("steps", run_index)
    collector_path = ("jobs", "failure-identity")
    mutations = [
        ("job masks failure", job_path + ("continue-on-error",), True),
        ("step masks failure", run_path + ("continue-on-error",), True),
        ("shell masks failure", run_path + ("run",), COMMAND + " || true"),
        ("shell disables fail-fast", run_path + ("run",), "set +e\n" + COMMAND),
        ("collector skips failed producer", collector_path + ("if",), "success()"),
        ("collector loses dependency", collector_path + ("needs",), []),
        ("collector missing report", collector_path + ("with", "expected-reports"), "[]"),
        ("collector unexpected report", collector_path + ("with", "expected-reports"),
         json.dumps(["junit-python-3.15/pytest-3.15.xml",
                     "junit-controlled-python-3.15/junit.xml", "unexpected/report.xml"])),
    ]
    for name in ("junit-python-3.15", "junit-controlled-python-3.15"):
        index = producer["steps"].index(_upload(producer, name))
        path = job_path + ("steps", index)
        mutations.extend([
            (name + " loses always", path + ("if",), None),
            (name + " ignores missing XML", path + ("with", "if-no-files-found"), "ignore"),
            (name + " retains raw for 90 days", path + ("with", "retention-days"), 90),
        ])
    for label, path, value in mutations:
        mutated = deepcopy(workflow)
        target = mutated
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        try:
            _assert_contract(mutated)
        except AssertionError:
            continue
        pytest.fail(f"unsafe workflow mutation escaped: {label}")


# ═══ 🚀 node launch ═══════════════════════════════════════════════════════════════════════════════════════
# Parity between legacy subprocess Node helpers and vendored njs_launch.

_STDIN_CLOSED_PAYLOAD = "x" * 70000 + "\n"
_BINARY_STDOUT = b"\xff\xfetest"


class _FakeNodeSpec(NamedTuple):
    version: str
    on_eval: str
    close_stdin_unread: bool = False
    stdin_close_exit_code: int = 3
    stdin_close_stdout: bytes = b""
    stdout_bytes: bytes = b""


_FAKE_NODE_SPECS: dict[str, _FakeNodeSpec] = {}


def _fake_node_key(path: Union[Path, str]) -> str:
    return str(Path(path).resolve())


class _StdinClosesEarly:
    def __init__(self, pipe_byte_limit: int = 4096) -> None:
        self._limit = pipe_byte_limit
        self._written = 0

    def write(self, data: bytes) -> int:
        if self._written >= self._limit:
            raise BrokenPipeError()
        remaining = self._limit - self._written
        if len(data) > remaining:
            self._written = self._limit
            raise BrokenPipeError()
        self._written += len(data)
        return len(data)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


def _run_fake_on_eval(on_eval: str) -> tuple[bytes, bytes, int]:
    from io import StringIO

    stdout = StringIO()
    stderr = StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    code = 0
    try:
        sys.stdout = stdout
        sys.stderr = stderr
        exec(on_eval, {"sys": sys})  # noqa: S102
    except SystemExit as exc:
        if exc.code is None:
            code = 0
        elif isinstance(exc.code, int):
            code = exc.code
        else:
            code = 1
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
    return (
        stdout.getvalue().encode("utf-8", errors="replace"),
        stderr.getvalue().encode("utf-8", errors="replace"),
        code,
    )


class _FakeNodePopen:
    def __init__(
        self,
        command: list[str],
        on_eval: str,
        *,
        close_stdin_unread: bool = False,
        stdin_close_exit_code: int = 3,
        stdin_close_stdout: bytes = b"",
        stdout_bytes: bytes = b"",
        **_kwargs: object,
    ) -> None:
        self.args = command
        self._on_eval = on_eval
        self._close_stdin_unread = close_stdin_unread
        self._stdin_close_exit_code = stdin_close_exit_code
        self._stdin_close_stdout = stdin_close_stdout
        self._stdout_bytes = stdout_bytes
        stdout_r, stdout_w = os.pipe()
        stderr_r, stderr_w = os.pipe()
        if close_stdin_unread:
            self.stdin = _StdinClosesEarly()
            self._stdin_r = None
        else:
            stdin_r, stdin_w = os.pipe()
            self.stdin = os.fdopen(stdin_w, "wb")
            self._stdin_r = stdin_r
        self.stdout = os.fdopen(stdout_r, "rb")
        self.stderr = os.fdopen(stderr_r, "rb")
        self._stdout_w = stdout_w
        self._stderr_w = stderr_w
        self.returncode: int | None = None
        self._done = threading.Event()

        def worker() -> None:
            if self._close_stdin_unread:
                try:
                    if self._stdin_close_stdout:
                        os.write(self._stdout_w, self._stdin_close_stdout)
                    if self._stdin_close_exit_code != 0:
                        os.write(self._stderr_w, b"boom\n")
                finally:
                    os.close(self._stdout_w)
                    os.close(self._stderr_w)
                    self.returncode = self._stdin_close_exit_code
                    self._done.set()
                return

            def drain_stdin() -> None:
                try:
                    with os.fdopen(self._stdin_r, "rb") as stream:
                        while stream.read(65536):
                            pass
                except OSError:
                    pass

            threading.Thread(target=drain_stdin, daemon=True).start()
            stdout, stderr, rc = _run_fake_on_eval(self._on_eval)
            if self._stdout_bytes:
                stdout = self._stdout_bytes
            try:
                if stdout:
                    os.write(self._stdout_w, stdout)
                if stderr:
                    os.write(self._stderr_w, stderr)
            finally:
                os.close(self._stdout_w)
                os.close(self._stderr_w)
                self.returncode = rc
                self._done.set()

        threading.Thread(target=worker, daemon=True).start()

    def wait(self, timeout: float | None = None) -> int:
        if not self._done.wait(timeout):
            raise subprocess.TimeoutExpired(self.args, timeout)
        return self.returncode if self.returncode is not None else -1

    def kill(self) -> None:
        self.returncode = -9
        self._done.set()


def _complete_fake_run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    spec = _FAKE_NODE_SPECS[_fake_node_key(argv[0])]
    proc = _FakeNodePopen(
        argv,
        spec.on_eval,
        close_stdin_unread=spec.close_stdin_unread,
        stdin_close_exit_code=spec.stdin_close_exit_code,
        stdin_close_stdout=spec.stdin_close_stdout,
        stdout_bytes=spec.stdout_bytes,
    )
    input_data = kwargs.get("input")
    if input_data is not None:
        payload = input_data.encode("utf-8") if isinstance(input_data, str) else input_data
        if proc.stdin is not None and hasattr(proc.stdin, "write"):
            try:
                proc.stdin.write(payload)
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass
    timeout = kwargs.get("timeout")
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise
    stdout = proc.stdout.read() if proc.stdout else b""
    stderr = proc.stderr.read() if proc.stderr else b""
    return subprocess.CompletedProcess(tuple(argv), rc, stdout, stderr)


@pytest.fixture(autouse=True)
def _njs_launch_process_layer_stub(monkeypatch):
    njs_launch = ui._njs_launch_module()
    real_run = njs_launch.subprocess.run
    real_popen = njs_launch.subprocess.Popen

    def fake_run(args, *pargs, **kwargs):
        if args and not isinstance(args, (str, bytes)):
            argv = list(args)
        else:
            argv = [args, *pargs]
        spec = _FAKE_NODE_SPECS.get(_fake_node_key(argv[0])) if argv else None
        if spec is not None and len(argv) >= 2 and argv[1] == "--version":
            return subprocess.CompletedProcess(
                tuple(argv), 0, (spec.version + "\n").encode(), b""
            )
        if spec is not None and not (len(argv) >= 2 and argv[1] == "--version"):
            return _complete_fake_run(argv, **kwargs)
        return real_run(args, *pargs, **kwargs)

    def fake_popen(command, **kwargs):
        argv = [os.fspath(part) for part in command]
        spec = _FAKE_NODE_SPECS.get(_fake_node_key(argv[0])) if argv else None
        if spec is None:
            return real_popen(command, **kwargs)
        return _FakeNodePopen(
            argv,
            spec.on_eval,
            close_stdin_unread=spec.close_stdin_unread,
            stdin_close_exit_code=spec.stdin_close_exit_code,
            stdin_close_stdout=spec.stdin_close_stdout,
            stdout_bytes=spec.stdout_bytes,
            **kwargs,
        )

    monkeypatch.setattr(njs_launch.subprocess, "run", fake_run)
    monkeypatch.setattr(njs_launch.subprocess, "Popen", fake_popen)
    yield
    _FAKE_NODE_SPECS.clear()


def _write_fake_node(
    tmp_path: Path,
    *,
    version: str,
    on_eval: str = "pass",
    close_stdin_unread: bool = False,
    stdin_close_exit_code: int = 3,
    stdin_close_stdout: bytes = b"",
    stdout_bytes: bytes = b"",
) -> Path:
    name = "fake_node.exe" if os.name == "nt" else "fake_node"
    dest = tmp_path / name
    dest.write_bytes(b"")
    _FAKE_NODE_SPECS[_fake_node_key(dest)] = _FakeNodeSpec(
        version,
        on_eval,
        close_stdin_unread=close_stdin_unread,
        stdin_close_exit_code=stdin_close_exit_code,
        stdin_close_stdout=stdin_close_stdout,
        stdout_bytes=stdout_bytes,
    )
    return dest


def _legacy_run_node(
    *argv: str | Path,
    timeout: float | None = 30,
    node: str | Path | None = None,
    input: str | bytes | None = None,
) -> subprocess.CompletedProcess[str]:
    executable = os.fspath(node) if node is not None else shutil.which("node")
    if executable is None:
        raise FileNotFoundError("node executable not found on PATH")
    command = [executable, *[str(argument) for argument in argv]]
    spec = _FAKE_NODE_SPECS.get(_fake_node_key(executable))
    if spec is not None:
        proc = _complete_fake_run(command, input=input, timeout=timeout)
        stdout = proc.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        stderr = proc.stderr.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)
    return subprocess.run(
        command,
        input=input,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _proc_bytes(proc: subprocess.CompletedProcess) -> tuple[int, bytes, bytes]:
    stdout = proc.stdout if isinstance(proc.stdout, bytes) else proc.stdout.encode()
    stderr = proc.stderr if isinstance(proc.stderr, bytes) else proc.stderr.encode()
    return proc.returncode, stdout, stderr


def _assert_same_outcome(old_call, new_call):
    try:
        old_value = old_call()
    except BaseException as old_exc:
        try:
            new_call()
        except BaseException as new_exc:
            assert type(old_exc) is type(new_exc), (old_exc, new_exc)
            if isinstance(old_exc, FileNotFoundError):
                assert new_exc.errno == old_exc.errno
            elif isinstance(old_exc, subprocess.TimeoutExpired):
                assert new_exc.timeout == old_exc.timeout
                assert new_exc.cmd == old_exc.cmd
            else:
                assert str(old_exc) == str(new_exc), (old_exc, new_exc)
            return
        raise AssertionError(f"legacy raised {old_exc!r}, new succeeded")
    new_value = new_call()
    assert _proc_bytes(old_value) == _proc_bytes(new_value)


def test_normal_run_matches_legacy(tmp_path):
    script = _write_fake_node(
        tmp_path,
        version="v26.0.0",
        on_eval="import sys; sys.stdout.write('ok\\n')",
    )
    script_path = tmp_path / "demo.js"
    script_path.write_text("export {}", encoding="utf-8")

    def old():
        return _legacy_run_node(script_path, node=script, timeout=30)

    def new():
        return ui.run_node(script_path, node=script, timeout=30)

    _assert_same_outcome(old, new)


def test_explicit_missing_node_path_raises_file_not_found(tmp_path):
    missing = tmp_path / "definitely-not-node"
    assert not missing.exists()
    script = tmp_path / "demo.js"
    script.write_text("", encoding="utf-8")

    def old():
        return _legacy_run_node(script, node=missing, timeout=30)

    def new():
        return ui.run_node(script, node=missing, timeout=30)

    with pytest.raises(FileNotFoundError) as old_exc:
        old()
    with pytest.raises(FileNotFoundError) as new_exc:
        new()
    assert new_exc.value.errno == errno.ENOENT
    assert str(missing) in (new_exc.value.filename or "")


def test_node_not_on_path_raises_runtime_error(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name, **kw: None)
    ui._njs_launch_module().clear_probe_cache()
    script = tmp_path / "check.mjs"
    script.write_text("", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="node executable not found on PATH"):
        _legacy_run_node(script, timeout=30)
    with pytest.raises(RuntimeError, match=r"Node 26 or newer.*not found on PATH"):
        ui.run_node(script, timeout=30)


def test_node_v20_on_path_names_found_version(tmp_path, monkeypatch):
    script = _write_fake_node(tmp_path, version="v20.0.0", on_eval="pass")
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name, **kw: str(script) if name == "node" else None,
    )
    ui._njs_launch_module().clear_probe_cache()
    with pytest.raises(RuntimeError, match=r"Node 26 or newer.*found Node 20"):
        ui.run_node(tmp_path / "check.mjs")


def test_node_v20_rejected_while_legacy_would_run(tmp_path):
    script = _write_fake_node(
        tmp_path,
        version="v20.0.0",
        on_eval="import sys; sys.stdout.write('legacy\\n')",
    )
    entry = tmp_path / "demo.js"
    entry.write_text("", encoding="utf-8")
    legacy = _legacy_run_node(entry, node=script, timeout=30)
    assert legacy.stdout == "legacy\n"
    with pytest.raises(RuntimeError, match=r"Node 26 or newer.*found Node 20"):
        ui.run_node(entry, node=script, timeout=30)


@pytest.mark.parametrize("major", [24, 25])
@pytest.mark.parametrize("explicit", [False, True])
def test_below_node_26_names_found_version(tmp_path, monkeypatch, major, explicit):
    script = _write_fake_node(tmp_path, version=f"v{major}.0.0", on_eval="pass")
    monkeypatch.setattr(shutil, "which", lambda name, **kw: str(script) if name == "node" else None)
    ui._njs_launch_module().clear_probe_cache()
    kwargs = {"node": script} if explicit else {}
    with pytest.raises(RuntimeError, match=rf"Node 26 or newer.*found Node {major}"):
        ui.run_node(tmp_path / "check.mjs", **kwargs)


def test_nonzero_exit_preserves_stderr(tmp_path):
    script = _write_fake_node(
        tmp_path,
        version="v26.0.0",
        on_eval="import sys; sys.stderr.write('diag\\n'); sys.exit(3)",
    )
    entry = tmp_path / "demo.js"
    entry.write_text("", encoding="utf-8")

    def old():
        return _legacy_run_node(entry, node=script, timeout=30)

    def new():
        return ui.run_node(entry, node=script, timeout=30)

    _assert_same_outcome(old, new)


def test_timeout_cmd_includes_resolved_node(tmp_path, monkeypatch):
    script = _write_fake_node(tmp_path, version="v26.0.0", on_eval="import time; time.sleep(60)")
    entry = tmp_path / "demo.js"
    entry.write_text("", encoding="utf-8")
    njs_launch = ui._njs_launch_module()

    def hang(*args, **kwargs):
        raise njs_launch.LaunchError(
            "njs_launch: Node process timed out",
            code="ELAUNCHFAILURE",
            stdout=b"",
            stderr=b"",
        )

    monkeypatch.setattr(njs_launch, "run", hang)
    with pytest.raises(subprocess.TimeoutExpired) as info:
        ui.run_node(entry, node=script, timeout=7)
    assert info.value.timeout == 7
    assert info.value.cmd == [str(script), str(entry)]


def test_timeout_matches_legacy(monkeypatch, tmp_path):
    script = _write_fake_node(tmp_path, version="v26.0.0", on_eval="pass")
    entry = tmp_path / "demo.js"
    entry.write_text("", encoding="utf-8")
    cmd = [str(script), str(entry)]
    timeout = 11.0
    njs_launch = ui._njs_launch_module()

    def launch_timeout(*args, **kwargs):
        raise njs_launch.LaunchError(
            "njs_launch: Node process timed out",
            code="ELAUNCHFAILURE",
            stdout=b"",
            stderr=b"",
        )

    monkeypatch.setattr(njs_launch, "run", launch_timeout)

    def old():
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    def new():
        return ui._web_ui_node_run(entry, node=script, timeout=timeout, check=False)

    _assert_same_outcome(old, new)


def test_stdin_closed_nonzero_returns_legacy_stderr(tmp_path):
    script = _write_fake_node(tmp_path, version="v26.0.0", close_stdin_unread=True)
    entry = tmp_path / "demo.js"
    entry.write_text("", encoding="utf-8")

    def old():
        return _legacy_run_node(entry, input=_STDIN_CLOSED_PAYLOAD, node=script, timeout=30)

    def new():
        return ui._web_ui_node_run(
            entry, input=_STDIN_CLOSED_PAYLOAD, node=script, timeout=30, check=False
        )

    old_proc = old()
    new_proc = new()
    assert old_proc.returncode == new_proc.returncode == 3
    assert new_proc.stderr == "boom\n"


def test_stdin_closed_zero_exit_returns_stdout(tmp_path):
    script = _write_fake_node(
        tmp_path,
        version="v26.0.0",
        close_stdin_unread=True,
        stdin_close_exit_code=0,
        stdin_close_stdout=b"done\n",
    )
    entry = tmp_path / "demo.js"
    entry.write_text("", encoding="utf-8")

    def old():
        return _legacy_run_node(entry, input=_STDIN_CLOSED_PAYLOAD, node=script, timeout=30)

    def new():
        return ui._web_ui_node_run(
            entry, input=_STDIN_CLOSED_PAYLOAD, node=script, timeout=30, check=False
        )

    _assert_same_outcome(old, new)


def test_bytes_stdout_preserved(tmp_path):
    script = _write_fake_node(
        tmp_path,
        version="v26.0.0",
        on_eval="pass",
        stdout_bytes=_BINARY_STDOUT,
    )
    entry = tmp_path / "demo.js"
    entry.write_text("", encoding="utf-8")
    njs_launch = ui._njs_launch_module()
    raw = njs_launch.run(entry, node=script, timeout=30, check=False)
    assert raw.stdout == _BINARY_STDOUT
    done = ui.run_node(entry, node=script, timeout=30)
    assert done.stdout == _BINARY_STDOUT.decode("utf-8", errors="replace")


def test_decode_node_process_bytes_normalizes_line_endings():
    assert ui._decode_node_process_bytes(b"a\r\nb\rc") == "a\nb\nc"
    assert ui._decode_node_process_bytes("x\r\ny\rz") == "x\ny\nz"


def test_run_node_normalizes_stdout_line_endings(tmp_path):
    script = _write_fake_node(
        tmp_path,
        version="v26.0.0",
        on_eval='import sys; sys.stdout.write("a\\r\\nb\\rc")',
    )
    result = ui.run_node(
        "-e",
        'process.stdout.write("a\\r\\nb\\rc")',
        node=script,
        timeout=30,
    )
    assert result.stdout == "a\nb\nc"


def test_timeout_expired_keeps_raw_output_and_stderr_bytes(tmp_path, monkeypatch):
    script = _write_fake_node(tmp_path, version="v26.0.0", on_eval="pass")
    entry = tmp_path / "demo.js"
    entry.write_text("", encoding="utf-8")
    njs_launch = ui._njs_launch_module()

    def timed_out(*args, **kwargs):
        raise njs_launch.LaunchError(
            "njs_launch: Node process timed out",
            code="ELAUNCHFAILURE",
            stdout=b"out\r\nline\r",
            stderr=b"err\r\n",
        )

    monkeypatch.setattr(njs_launch, "run", timed_out)
    with pytest.raises(subprocess.TimeoutExpired) as info:
        ui.run_node(entry, node=script, timeout=3)
    assert info.value.output == b"out\r\nline\r"
    assert info.value.stderr == b"err\r\n"


def _pytest_on_mutated_web_ui(replacements: list[tuple[str, str]], test_id: str) -> int:
    with tempfile.TemporaryDirectory() as directory:
        overlay = Path(directory)
        shutil.copytree(ROOT / "vendor", overlay / "vendor")
        source = (ROOT / "pysaiyanweboo.py").read_text(encoding="utf-8")
        for old, new in replacements:
            if source.count(old) != 1:
                raise AssertionError(f"mutation anchor must appear once: {old!r}")
            source = source.replace(old, new, 1)
        (overlay / "pysaiyanweboo.py").write_text(source, encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(overlay) + os.pathsep + env.get("PYTHONPATH", "")
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", test_id, "-q", "--tb=no"],
            cwd=ROOT,
            env=env,
            check=False,
        )
        return completed.returncode


def test_mutation_subprocess_broken_decode_fails_line_ending_test():
    rc = _pytest_on_mutated_web_ui(
        [
            (
                '    return text.replace("\\r\\n", "\\n").replace("\\r", "\\n")',
                "    return text",
            )
        ],
        f"{__name__}::test_run_node_normalizes_stdout_line_endings",
    )
    assert rc != 0


def test_mutation_subprocess_broken_raise_fails_v20_path_test():
    rc = _pytest_on_mutated_web_ui(
        [
            (
                "                njs_launch._probe_node_once(discovered, njs_launch.DEFAULT_PROBE_TIMEOUT)",
                "                pass  # mutation: skip PATH version reprobe",
            )
        ],
        f"{__name__}::test_node_v20_on_path_names_found_version",
    )
    assert rc != 0


def test_mutation_subprocess_broken_run_fails_normal_parity_test():
    rc = _pytest_on_mutated_web_ui(
        [
            (
                "            completed = njs_launch.run(",
                "            completed = subprocess.CompletedProcess(command, 0, b\"mutated\", b\"\")  # mutation\n            if False: njs_launch.run(",
            )
        ],
        f"{__name__}::test_normal_run_matches_legacy",
    )
    assert rc != 0


def test_run_node_without_argv_matches_legacy_bare_node(tmp_path):
    script = _write_fake_node(
        tmp_path,
        version="v26.0.0",
        on_eval="import sys; sys.stdout.write('bare\\n')",
    )

    def old():
        return _legacy_run_node(node=script, timeout=30)

    def new():
        return ui.run_node(node=script, timeout=30)

    _assert_same_outcome(old, new)


# ═══ 🩺 repository diagnostics ════════════════════════════════════════════════════════════════════════════

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pysaiyanweboo  # noqa: E402
import pytest  # noqa: E402
from support import node26, node_js  # noqa: E402
JS = pysaiyanweboo.js_source("repository-diagnostics.js")
CSS = pysaiyanweboo.css_source("repository-diagnostics.css")


@pytest.mark.skipif(not node26(), reason="run_node requires Node 26+")
def test_renderer_contract_in_node():
    # repository-diagnostics.js in Node: commit line, escaped render, observation cards (https links only) and mount() with a fake fetch.
    diagnostics_js = r"""const fs = require("fs");
const path = require("path");
const assert = require("assert");
const renderer = require("./js/repository-diagnostics.js");

const fixturePath = path.join(REPO, "tests", "fixtures", "repository_metadata_v1.json");
const record = JSON.parse(fs.readFileSync(fixturePath, "utf8"));

assert.strictEqual(
  renderer.commitLine(record),
  "Commit 1376c703 · main · 2026-09-27T19:09:22+09:00 · chore: refresh metadata"
);

const html = renderer.render(record);
assert(html.includes("myon-bioinformatics/Ironmate"));
assert(html.includes("not measured"));
assert(html.includes("1.12 MiB"));

const hostile = JSON.parse(JSON.stringify(record));
hostile.repository.full_name = "<img src=x onerror=alert(1)>";
hostile.head.subject = "<script>alert(1)</script>";
const escaped = renderer.render(hostile);
assert(!escaped.includes("<script>"));
assert(!escaped.includes("<img src=x"));
assert(escaped.includes("&lt;script&gt;"));
assert(escaped.includes("&lt;img src=x onerror=alert(1)&gt;"));

const invalid = JSON.parse(JSON.stringify(record));
invalid.measurements.working_tree_bytes = -5;
assert.throws(() => renderer.render(invalid), /invalid byte measurement/);

// The resolver part: a card per observation, values escaped, a link only for https:// (never javascript:).
const resolver = {auth: "anonymous", status: "ok", observations: [
  {kind: "repository", status: "public", http_status: 200, url: "https://github.com/myon-bioinformatics/Ironmate"},
  {kind: "<b>pages</b>", status: "missing", http_status: null, url: "javascript:alert(1)"}]};
assert.strictEqual(renderer.summaryLine(resolver), "Auth: anonymous \u00b7 Status: ok");
const cards = renderer.renderObservations(resolver);
assert.strictEqual((cards.match(/<article class="ui-card">/g) || []).length, 2);
assert(cards.includes('<a href="https://github.com/myon-bioinformatics/Ironmate" target="_blank" rel="noopener">'));
assert(cards.includes("<span>javascript:alert(1)</span>") && !cards.includes('href="javascript'));
assert(cards.includes("&lt;b&gt;pages&lt;/b&gt;") && cards.includes("HTTP: not observed") && cards.includes("HTTP: 200"));

// mount(document, url): one no-store GET fills #metadata, #summary and #observations; a failed GET says so and leaves no cards.
function page() {
  const ids = {metadata: {innerHTML: ""}, summary: {textContent: "Loading\u2026"}, observations: {innerHTML: "x"}};
  return {ids, getElementById: id => ids[id]};
}
(async () => {
  const seen = [], realFetch = globalThis.fetch;
  try {
    globalThis.fetch = (url, opts) => { seen.push([url, opts.cache]); return Promise.resolve({ok: true, json: () => Promise.resolve({metadata: record, resolver})}); };
    const ok = page();
    await renderer.mount(ok, "./repository-diagnostics.json");
    assert.deepStrictEqual(seen, [["./repository-diagnostics.json", "no-store"]]);
    assert(ok.ids.metadata.innerHTML.includes("myon-bioinformatics/Ironmate"));
    assert.strictEqual(ok.ids.summary.textContent, "Auth: anonymous \u00b7 Status: ok");
    assert.strictEqual(ok.ids.observations.innerHTML, cards);
    globalThis.fetch = () => Promise.resolve({ok: false});
    const bad = page();
    await renderer.mount(bad, "./missing.json");
    assert.strictEqual(bad.ids.summary.textContent, "Diagnostics could not be loaded.");
    assert.strictEqual(bad.ids.observations.innerHTML, "");
  } finally { globalThis.fetch = realFetch; }
  console.log("repository-diagnostics.js ok");
})().catch(error => { console.error(error); process.exitCode = 1; });

// Observation cards and the summary line are rendered by the same module, escaped the same way.
{
  const resolver = {auth: "anonymous", status: "observed", observations: [
    {kind: "pages", status: "#reachable", http_status: 200, url: "https://example.test/<x>"},
    {kind: "api", status: "#unverified", http_status: null, url: "https://example.test/api"},
  ]};
  assert.strictEqual(renderer.summaryLine(resolver), "Auth: anonymous \u00b7 Status: observed");
  assert.strictEqual(renderer.summaryLine(null), "Auth: unknown \u00b7 Status: unknown");
  const cards = renderer.renderObservations(resolver);
  assert.strictEqual((cards.match(/<article class="ui-card">/g) || []).length, 2);
  assert(cards.includes("HTTP: 200") && cards.includes("HTTP: not observed"));
  assert(cards.includes("https://example.test/&lt;x&gt;") && !cards.includes("<x>"));
  assert.strictEqual(renderer.renderObservations({}), "");
  assert.strictEqual(typeof renderer.mount, "function");
}"""
    assert "repository-diagnostics.js ok" in node_js(diagnostics_js).stdout


def test_renderer_is_reusable_and_schema_gated():
    assert "global.RepositoryDiagnostics = api" in JS
    assert 'record.schema_version !== "1.0"' in JS
    assert "Commit " in JS
    assert "not measured" in JS


def test_renderer_escapes_dynamic_content():
    assert "function esc(value)" in JS
    assert "esc(commitLine(record))" in JS
    assert "esc(record.repository.full_name)" in JS


def test_renderer_has_responsive_component_css():
    assert ".repo-diagnostics" in CSS
    assert "@media(max-width:30rem)" in CSS
    assert "font-variant-numeric:tabular-nums" in CSS


def test_renderer_requires_repository_identity():
    assert 'typeof record.repository.full_name !== "string"' in JS
    assert 'class="repo-diagnostics__repository"' in JS


def test_the_page_body_is_also_the_component():
    """repository_diagnostics_body() is the page's body (the page itself is unchanged), so a page of your own or COMPONENTS reuse it."""
    import pytest
    body = pysaiyanweboo.repository_diagnostics_body("myon-bioinformatics/ascii_artist")
    page = pysaiyanweboo.repository_diagnostics_page("myon-bioinformatics/ascii_artist")
    assert '<main class="ui-page">' + body + "</main>" in page and "<script" not in body
    assert body.startswith('<img src="./icon.png" width="80" height="80"') and 'id="metadata"' in body and 'id="observations"' in body
    parts = pysaiyanweboo.component_parts("repository-diagnostics", "x/y")
    assert parts["html"] == pysaiyanweboo.repository_diagnostics_body("x/y") and parts["css"] == CSS
    assert parts["js"] == JS + '\nRepositoryDiagnostics.mount(document, "./repository-diagnostics.json");\n'
    for bad in ({"icon": "data:image/png;base64,AAAA"}, {"json_name": "../x.json?y"}):
        with pytest.raises(ValueError):
            pysaiyanweboo.repository_diagnostics_body("o/r", **bad)
    assert "<span>' + esc(url) + '</span>" in JS                                   # a link only for https://, other URLs as text


def test_renderer_mounts_the_page_from_one_json():
    assert "function renderObservations(resolver)" in JS and "function mount(doc, url)" in JS
    assert 'summary.textContent = "Diagnostics could not be loaded."' in JS
    assert "esc(item && item.kind" in JS and 'esc(url)' in JS


def test_repository_diagnostics_page_is_self_contained():
    html = pysaiyanweboo.repository_diagnostics_page("myon-bioinformatics/markdown")
    assert html.startswith("<!doctype html>")
    assert "<title>myon-bioinformatics/markdown repository diagnostics</title>" in html
    assert "cdn.jsdelivr.net" not in html and "<link rel=\"stylesheet\"" not in html
    assert "/* css/repository-diagnostics.css */" in html and "/* css/themes/modern.css */" in html
    assert "global.RepositoryDiagnostics = api" in html
    assert 'RepositoryDiagnostics.mount(document, "./repository-diagnostics.json");' in html
    assert 'href="./repository-diagnostics.jsonl"' in html and 'src="./icon.png"' in html
    assert 'href="./favicon.png"' in html and 'rel="apple-touch-icon" href="./icon.png"' in html
    assert '<body data-ui-theme="modern">' in html


def test_repository_diagnostics_page_options_and_rejections():
    import pytest
    html = pysaiyanweboo.repository_diagnostics_page("o/r", theme="github-like", icon=None, favicon=None, json_name="d.json", jsonl_name="d.jsonl")
    assert '<body data-ui-theme="github-like">' in html and "<img" not in html and 'mount(document, "./d.json")' in html
    for repository in ("markdown", "o/r/x", "<b>/r", ""):
        with pytest.raises(ValueError):
            pysaiyanweboo.repository_diagnostics_page(repository)
    with pytest.raises(ValueError):
        pysaiyanweboo.repository_diagnostics_page("o/r", json_name="../x.json?y")
    with pytest.raises(ValueError):
        pysaiyanweboo.repository_diagnostics_page("o/r", theme="nope")


def test_table_escapes_and_classes():
    import pytest
    html = pysaiyanweboo.table(("Env", "Verdict"), [("linux-chromium", "pass"), ("<x>", None)], caption="c", id="facts",
                        row_classes=["ui-pass", None])
    assert html.startswith('<table class="ui-table" id="facts"><caption>c</caption><thead><tr><th scope="col">Env</th>')
    assert '<tr class="ui-pass"><td>linux-chromium</td><td>pass</td></tr><tr><td>&lt;x&gt;</td><td></td></tr>' in html
    assert pysaiyanweboo.table(("a",), [("<b>bold</b>",)], trusted_html=True).count("<b>bold</b>") == 1
    with pytest.raises(ValueError):
        pysaiyanweboo.table(("a",), [("1", "2")])
    with pytest.raises(ValueError):
        pysaiyanweboo.table(("a",), [("1",)], row_classes=[])
    assert ".ui-table,.ui-elements table{" in pysaiyanweboo.css_source("components.css")


def test_terminal_is_a_token_only_theme():
    tokens = pysaiyanweboo.css_source("tokens.css")
    assert "terminal" in pysaiyanweboo.CANDIDATE_THEMES
    assert 'body[data-ui-theme="terminal"]{--ui-bg:#0a0e10;' in tokens and "--ui-font:var(--ui-font-mono)" in tokens
    assert "color-scheme:dark" in tokens.split('body[data-ui-theme="terminal"]')[1].split("}")[0]
    assert '<body data-ui-theme="terminal">' in pysaiyanweboo.render_document("x", theme="terminal")
    glyphs = pysaiyanweboo.css_source("themes/terminal.css")  # presentation only; the palette stays in tokens.css
    assert "--ui-" not in glyphs.split("{", 1)[0] and 'body[data-ui-theme="terminal"] .ui-title::before{content:"# "' in glyphs
    assert "/* css/themes/terminal.css */" in pysaiyanweboo.core_css("terminal")


def test_core_css_is_the_small_bundle():
    import pytest
    core = pysaiyanweboo.core_css()
    assert core.startswith("@layer base,components,theme;") and "/* css/themes/modern.css */" in core
    assert ".ui-table,.ui-elements table{" in core and ".ui-pass{" in core and "/* css/shell.css */" not in core
    assert len(core) < 6000 < len(pysaiyanweboo.bundled_css())
    assert 'body[data-ui-theme="terminal"]' in pysaiyanweboo.core_css("terminal") and 'body[data-ui-theme="green"]' in pysaiyanweboo.core_css("green")
    with pytest.raises(ValueError):
        pysaiyanweboo.core_css("nope")
    assert ".ui-tag.ui-pass{" in pysaiyanweboo.css_source("components.css")


def test_theme_css_registers_a_consumer_palette():
    import pytest
    css = pysaiyanweboo.theme_css("ironmate", {"--ui-bg": "#edf0ec", "--ui-fg": "#213a3c", "--ui-accent": "#087d79"})
    assert css == '@layer theme{body[data-ui-theme="ironmate"]{--ui-bg:#edf0ec;--ui-fg:#213a3c;--ui-accent:#087d79;color-scheme:light}}\n'
    assert "color-scheme:dark" in pysaiyanweboo.theme_css("night", {"--ui-bg": "#000000"})
    for name, tokens in (("Bad", {"--ui-bg": "#fff"}), ("x", {"--ui-fg": "#fff"}), ("x", {"--ui-bg": "#fff", "color": "red"})):
        with pytest.raises(ValueError):
            pysaiyanweboo.theme_css(name, tokens)
    assert '<body data-ui-theme="ironmate">' in pysaiyanweboo.render_document("x", theme="ironmate")  # registered above
    with pytest.raises(ValueError):
        pysaiyanweboo.render_document("x", theme="never-registered")
    assert '<body data-ui-theme="auto">' in pysaiyanweboo.render_document("x", theme="auto")


def test_ui_elements_opt_in_styles_bare_form_elements():
    css = pysaiyanweboo.css_source("components.css")
    assert ".ui-elements button," in css and ".ui-elements textarea," in css and ".ui-elements table{" in css
    assert "[type=checkbox],[type=radio],[type=range],[type=color],[type=file])" in css
    assert ".ui-elements button:hover{border-color:var(--ui-accent)}" in css


def test_write_bundle_and_check_bundle_round_trip(tmp_path):
    import hashlib
    import subprocess
    import sys
    brand = ("acme", {"--ui-bg": "#ffffff", "--ui-fg": "#000000"})
    target = tmp_path / "site.css"
    fields = pysaiyanweboo.write_bundle(target, theme="terminal", brand=brand, extra_css=".x{}", note="scripts/x.py")
    text = target.read_text(encoding="utf-8")
    head, body = text.split("\n", 1)
    assert head == f"/* web-ui-bundle/1 commit={fields['commit']} sha256={hashlib.sha256(body.encode()).hexdigest()} scripts/x.py*/"
    assert fields["commit"] == (pysaiyanweboo.source_commit() or "unknown")
    assert body == pysaiyanweboo.core_css("terminal") + pysaiyanweboo.theme_css(*brand) + ".x{}"
    assert pysaiyanweboo.check_bundle(target, theme="terminal", brand=brand, extra_css=".x{}") == []
    assert "stale" in pysaiyanweboo.check_bundle(target, theme="terminal")[0]
    target.write_text(text + "/*hand*/", encoding="utf-8")
    assert "sha256" in pysaiyanweboo.check_bundle(target, theme="terminal", brand=brand, extra_css=".x{}")[0]
    assert pysaiyanweboo.check_bundle(tmp_path / "none.css")
    import pytest
    with pytest.raises(ValueError):
        pysaiyanweboo.write_bundle(target, note="two\nlines")
    second = tmp_path / "second.css"
    pysaiyanweboo.write_bundle(second, theme=None, extra_css=".y{}")  # a sheet loaded after the first: no second core
    assert second.read_text(encoding="utf-8").split("\n", 1)[1] == ".y{}"
    assert pysaiyanweboo.check_bundle(second, theme=None, extra_css=".y{}") == []
    # The CLI is the same two calls, so Node (vendor/py_launch.cjs) and python -S consumers get the same bytes.
    spec = tmp_path / "brand.json"
    spec.write_text('{"name": "acme", "tokens": {"--ui-bg": "#ffffff", "--ui-fg": "#000000"}}', encoding="utf-8")
    (tmp_path / "extra.css").write_text(".x{}", encoding="utf-8")
    cli = [sys.executable, "-S", str(ROOT / "pysaiyanweboo.py"), "--theme", "terminal", "--brand", str(spec), "--extra-css", str(tmp_path / "extra.css")]
    assert subprocess.run([*cli, "--bundle", str(target), "--note", "scripts/x.py"], capture_output=True, text=True).returncode == 0
    assert target.read_text(encoding="utf-8").split("\n", 1)[1] == body
    assert subprocess.run([*cli, "--bundle-check", str(target)], capture_output=True, text=True).returncode == 0
    assert subprocess.run([sys.executable, "-S", str(ROOT / "pysaiyanweboo.py"), "--bundle-check", str(target)], capture_output=True, text=True).returncode == 1


def test_source_commit_is_the_checkout_head_or_the_install_record():
    commit = pysaiyanweboo.source_commit()
    assert commit is None or (len(commit) == 40 and int(commit, 16) >= 0)


def test_check_theme_reads_every_palette_we_ship_and_names_what_fails():
    for name, tokens in pysaiyanweboo.theme_palettes().items():
        assert pysaiyanweboo.check_theme(tokens) == [], name
    for hue in (0.0, 0.17, 0.5, 0.83):
        for dark in (False, True):
            assert pysaiyanweboo.check_theme(pysaiyanweboo.theme_palette(hue, dark=dark)) == [], (hue, dark)
    pale = {"--ui-bg": "#edf0ec", "--ui-panel": "#ffffff", "--ui-fg": "#213a3c", "--ui-muted": "#657970",
            "--ui-border": "#d9e0d9", "--ui-accent": "#087d79", "--ui-danger": "#bc4e40"}
    problems = pysaiyanweboo.check_theme(pale)
    assert any(p.startswith("--ui-muted #657970 on --ui-bg #edf0ec: contrast 4.04 < 4.5") for p in problems)
    assert any(p.startswith("--ui-border") for p in problems) and not any("--ui-fg" in p for p in problems)
    assert pysaiyanweboo.check_theme(pale, minimum=4.0, border_minimum=1.1) == []
    assert pysaiyanweboo.check_theme({"--ui-bg": "#fff"})[0] == "--ui-bg: '#fff' is not #rrggbb"


def test_every_page_says_which_web_ui_drew_it():
    page = pysaiyanweboo.render_document("x")
    match = pysaiyanweboo.GENERATOR_META.search(page)
    assert match and match.group(1) == (pysaiyanweboo.installed_commit() or "checkout")  # never the checkout's HEAD: it moves
    assert page.index('name="generator"') < page.index("<title>")
    assert pysaiyanweboo.GENERATOR_META.search(pysaiyanweboo.repository_diagnostics_page("o/r"))


def test_core_prints_and_respects_reduced_motion_and_auto_scheme():
    base = pysaiyanweboo.css_source("base.css")
    assert "@media print{body{background:#fff;color:#000}" in base and ".ui-no-print{display:none}" in base
    assert ".ui-print-only{display:none}" in base and "@media(prefers-reduced-motion:reduce)" in base
    tokens = pysaiyanweboo.css_source("tokens.css")
    assert 'body[data-ui-theme="auto"]{color-scheme:dark light}' in tokens
    light = tokens.split('@media(prefers-color-scheme:light){body[data-ui-theme="auto"]{', 1)[1].split("}", 1)[0]
    assert "--ui-bg:#ffffff" in light and "--ui-accent:#0969da" in light  # the github-like palette, not a copy
    assert "/* css/tokens.css */" in pysaiyanweboo.core_css("auto") and "themes/" not in pysaiyanweboo.core_css("auto")


def test_page_document_builds_a_page_from_a_spec(tmp_path):
    import pytest
    import subprocess
    import sys
    spec = pysaiyanweboo.EXAMPLES["page"]
    page = pysaiyanweboo.page_document(spec, layouts=pysaiyanweboo.EXAMPLES["page-layouts"])
    assert page.startswith("<!doctype html>") and '<h1 class="ui-title">Run report</h1>' in page
    assert '<span class="ui-tag ui-pass">12 pass</span>' in page and '<dl class="ui-kv"><dt>commit</dt><dd>abc1234</dd>' in page
    assert '<caption>per environment</caption>' in page and '<section class="ui-panel"><h2>Detail</h2><p class="ui-muted">Two paragraphs,</p><p class="ui-muted">separated' in page
    assert '<pre class="ui-output">$ run\nok</pre>' in page and '<a href="./receipt.json">receipt</a>' in page
    assert 'name="ui-layout"' in page and ":root{--ui-text:16px" in page and "/* css/components.css */" in page
    hostile = {"schema": "web-ui-page/1", "title": "<b>", "blocks": [{"type": "text", "text": "<script>"}, {"type": "table", "headers": ["<h>", "n"], "rows": [["<c>", 1]]}]}
    out = pysaiyanweboo.page_document(hostile)
    assert "<script>" not in out and "&lt;b&gt;" in out and "&lt;h&gt;" in out and "<td>1</td>" in out
    for bad in ({"schema": "nope"}, {**spec, "extra": 1}, {**spec, "theme": "never"},
                {**spec, "blocks": [{"type": "links", "items": [{"href": "javascript:alert(1)"}]}]},
                {**spec, "blocks": [{"type": "image", "src": "//evil/x.png"}]},
                {**spec, "blocks": [{"type": "heading", "text": "x", "level": 7}]},
                {**spec, "blocks": [{"type": "card", "blocks": [{"type": "card", "blocks": [{"type": "card", "blocks": [{"type": "card", "blocks": []}]}]}]}]},
                {**spec, "blocks": [{"type": "what"}]}):
        with pytest.raises(ValueError):
            pysaiyanweboo.page_document(bad)
    pysaiyanweboo.theme_css("acme", {"--ui-bg": "#ffffff", "--ui-fg": "#000000"})
    branded = pysaiyanweboo.page_document({**spec, "theme": "acme"})
    assert '<body data-ui-theme="acme">' in branded and 'body[data-ui-theme="acme"]{--ui-bg:#ffffff' in branded
    (tmp_path / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    done = subprocess.run([sys.executable, "-S", str(ROOT / "pysaiyanweboo.py"), "--page", str(tmp_path / "spec.json")], capture_output=True, text=True)
    assert done.returncode == 0 and pysaiyanweboo.GENERATOR_META.sub("", done.stdout) == pysaiyanweboo.GENERATOR_META.sub("", pysaiyanweboo.page_document(spec))


def test_parts_document_shows_every_theme_in_its_own_frame():
    import pytest
    page = pysaiyanweboo.parts_document()
    assert page.count("<iframe") == len(pysaiyanweboo.PARTS_THEMES) == 8 and 'sandbox="allow-same-origin"' in page   # purple joined the candidates
    for theme in pysaiyanweboo.PARTS_THEMES:
        assert f'id="theme-{theme}"' in page and f'data-ui-theme=&quot;{theme}&quot;' in page
    assert "<script" not in page and page.count("type=&quot;radio&quot; name=&quot;ui-layout&quot;") == len(pysaiyanweboo.PARTS_THEMES) * 4
    pysaiyanweboo.theme_css("acme", {"--ui-bg": "#ffffff", "--ui-fg": "#000000"})
    assert pysaiyanweboo.parts_document(themes=("modern", "acme")).count("<iframe") == 2
    with pytest.raises(ValueError):
        pysaiyanweboo.parts_document(themes=("never",))
    assert "examples/parts.html" in pysaiyanweboo.example_pages()


# ═══ 📄 single file ═══════════════════════════════════════════════════════════════════════════════════════
# Exercise copied artifacts in isolated stdlib-only interpreters.

def test_embedded_launcher_matches_locked_vendor():
    assert pysaiyanweboo._EMBEDDED_NJS_LAUNCH_SOURCE.encode() == (ROOT / 'vendor/njs_launch.py').read_bytes()


@pytest.mark.parametrize('vendor', [False, True])
@pytest.mark.parametrize('case', ['html', 'success', 'nonzero', 'timeout', 'missing', 'old'])
def test_copied_artifact(tmp_path, vendor, case):
    shutil.copyfile(ROOT / 'pysaiyanweboo.py', tmp_path / 'pysaiyanweboo.py')
    if vendor:
        (tmp_path / 'vendor').mkdir()
        shutil.copyfile(ROOT / 'vendor/njs_launch.py', tmp_path / 'vendor/njs_launch.py')
    code = '''
import pysaiyanweboo as u
import subprocess
'''
    code += {
        'html': '''
u.shutil.which = lambda *a: None
assert 'hello' in u.render_document('hello')
assert u._NJS_LAUNCH is None
''',
        'success': '''
p = u.run_node('-e', 'process.stdout.write("hello"+String.fromCharCode(13,10)); process.stderr.write("err"+String.fromCharCode(13));')
assert (p.returncode, p.stdout, p.stderr) == (0, 'hello\\n', 'err\\n')
assert u.run_node(input='console.log(42)').stdout == '42\\n'
''',
        'nonzero': '''
p = u.run_node('-e', 'console.error("bad"); process.exit(7)')
assert p.returncode == 7 and p.stderr == 'bad\\n'
try:
    u.run_node('-e', 'process.exit(7)', check=True)
except u._njs_launch_module().LaunchError as e:
    assert e.status == 7
else:
    raise AssertionError('missing CalledProcessError')
''',
        'timeout': '''
try:
    u.run_node('-e', 'console.log("ready"); console.error("waiting"); setTimeout(()=>{}, 30000)', timeout=1)
except subprocess.TimeoutExpired as e:
    assert e.output == b'ready\\n' and e.stderr == b'waiting\\n'
else:
    raise AssertionError('missing timeout')
''',
        'missing': '''
u.shutil.which = lambda *a: None
try:
    u.run_node('-e', '42')
except RuntimeError as e:
    assert 'node executable not found' in str(e)
else:
    raise AssertionError('missing failure')
''',
        'old': '''
launcher = u._njs_launch_module()
launcher.subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a[0], 0, b'v20.0.0', b'')
try:
    u.run_node('-e', '42')
except RuntimeError as e:
    assert 'found Node 20' in str(e)
else:
    raise AssertionError('old Node accepted')
''',
    }[case]
    done = subprocess.run([sys.executable, '-I', '-S', '-c',
                           'import sys; sys.path.insert(0, ' + repr(str(tmp_path)) + ');' + code],
                          cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert done.returncode == 0, done.stderr


def test_one_module_and_no_old_name():
    """pysaiyanweboo.py is the only module: the forwarding file web_ui.py is gone and is not installed."""
    import tomllib
    assert not (ROOT / 'web_ui.py').exists()
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    assert project['tool']['setuptools']['py-modules'] == ['pysaiyanweboo']


# ═══ 🤖 vendor automation ═════════════════════════════════════════════════════════════════════════════════
# Vendor lock CI workflow regression tests.

CI_WORKFLOW_NAME = ".github/workflows/ci.yml"
TEST_JOB = "tooling"
PIN = "26c442bc51b8a2837fe2556782b2937f396932af"


def _lock_entries(root=ROOT):
    lock = json.loads((root / "vendor.lock.json").read_text(encoding="utf-8"))
    assert lock["schema"] == "vendor-lock/1"
    return lock["files"]


def _workflow():
    import yaml

    return yaml.load((ROOT / CI_WORKFLOW_NAME).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _copy_snapshot(root):
    snapshot = ["vendor.lock.json", *[e["destination"] for e in _lock_entries()]]
    for name in snapshot:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)


def test_vendor_lock_lists_expected_sources():
    expected = {
        ("myon-bioinformatics/Ironmate", "LICENSE", "tools/vendor/LICENSE"),
        (
            "myon-bioinformatics/myon-bioinformatics",
            "njs_launch.py",
            "vendor/njs_launch.py",
        ),
        ("myon-bioinformatics/myon-bioinformatics", "py_launch.cjs", "vendor/py_launch.cjs"),
    }
    actual = {(e["repository"], e["source"], e["destination"]) for e in _lock_entries()}
    assert actual == expected
    assert all(e["ref"] == e["commit"] for e in _lock_entries())


@pytest.mark.parametrize("destination,commit", [("vendor/njs_launch.py", "0d20801e2e372a72426ce85cee7ac04d701e71b5"),   # the rename's merge (parent #266)
                                                ("vendor/py_launch.cjs", "384f5dd532076062f7833038764e9a62322c387c")])
def test_launchers_pin_the_accepted_parent_merge(destination, commit):
    entry = next(e for e in _lock_entries() if e["destination"] == destination)
    assert entry["repository"] == "myon-bioinformatics/myon-bioinformatics"
    assert entry["ref"] == entry["commit"] == commit
    data = (ROOT / destination).read_bytes()
    assert hashlib.sha256(data).hexdigest() == entry["sha256"]
    assert hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() == entry["blob_sha"]


def test_public_vendor_ci_updates_without_repository_writes():
    ci = _workflow()
    assert {"push", "pull_request"} <= set(ci["on"])
    assert "schedule" not in ci["on"]
    assert ci.get("permissions", {"contents": "read"}) == {"contents": "read"}
    jobs = ci["jobs"]
    for job in (jobs["resolve-vendor"], jobs[TEST_JOB]):
        assert "continue-on-error" not in job
    resolve = jobs["resolve-vendor"]["steps"]
    test = jobs[TEST_JOB]["steps"]
    assert jobs["resolve-vendor"]["permissions"] == jobs[TEST_JOB]["permissions"] == {"contents": "read"}
    assert not any(s.get("name") == "Update public vendor files for this run" for s in resolve)
    assert not any("vendor_sync.py promote" in s.get("run", "") for steps in (resolve, test) for s in steps)
    assert not any("vendor_sync.py update" in s.get("run", "") for steps in (resolve, test) for s in steps)
    assert not any("sync_vendor_provenance" in s.get("run", "") for steps in (resolve, test) for s in steps)
    recreate = next(s for s in resolve if s.get("name") == "Recreate locked vendor files from GitHub")
    assert recreate["shell"] == "bash"
    assert recreate["run"].splitlines() == [
        "python -S .vendor-sync-tools/vendor_sync.py recreate --manifest vendor.lock.json",
    ]
    needs = jobs[TEST_JOB]["needs"]
    assert "resolve-vendor" in ([needs] if isinstance(needs, str) else needs)
    download = next(i for i, s in enumerate(test) if s.get("name") == "Download resolved vendor snapshot")
    verify = next(i for i, s in enumerate(test) if s.get("name") == "Verify resolved vendor snapshot")
    tests = [i for i, s in enumerate(test) if "pytest " in s.get("run", "")]
    assert tests and download < verify < min(tests)
    assert test[download]["with"]["name"] == "vendor-snapshot"
    assert test[verify]["run"].splitlines() == [
        "python -S .vendor-sync-tools/vendor_sync.py check --manifest vendor.lock.json",
    ]
    for steps, name in (
        (resolve, "Preserve resolved vendor snapshot"),
        (test, "Preserve vendor lock used by this run"),
    ):
        upload = next(s for s in steps if s.get("name") == name)
        assert upload["if"] == "always()"
        assert upload["with"]["if-no-files-found"] == "error"
        assert upload["with"]["path"].startswith("build/vendor-evidence-")
    pins = [
        s["with"]["ref"]
        for steps in (resolve, test)
        for s in steps
        if s.get("with", {}).get("repository") == "myon-bioinformatics/myon-bioinformatics"
    ]
    assert pins == [PIN] * 2
    for steps in (resolve, test):
        for step in steps:
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] == "false"
            assert not any(
                x in step.get("run", "") for x in ("|| true", "|| :", "set +e", "git push", "git commit", "gh pr")
            )
            assert "continue-on-error" not in step
    text = (ROOT / CI_WORKFLOW_NAME).read_text(encoding="utf-8")
    assert not any(x in text for x in ("secrets.", "VENDOR_UPDATE_TOKEN", "VENDOR_UPDATES_ENABLED", "GH_TOKEN"))
    assert "vendor-mode" not in text
    assert "provenance.json" not in text


def test_locked_baseline_runs_automatically_without_candidate_snapshot():
    ci = _workflow()
    job = ci["jobs"]["vendor-locked"]
    assert job["permissions"] == {"contents": "read"}
    assert "continue-on-error" not in job
    assert job.get("needs") == ci["jobs"]["resolve-vendor"].get("needs")
    assert job.get("if") == ci["jobs"]["resolve-vendor"].get("if")
    matrix = job.get("strategy", {}).get("matrix", {})
    assert matrix == {"node-version": ["26", "latest"]}
    steps = job["steps"]
    assert not any("vendor_sync.py promote" in s.get("run", "") for s in steps)
    assert not any("vendor_sync.py update" in s.get("run", "") for s in steps)
    assert not any(s.get("uses", "").startswith("actions/download-artifact@") for s in steps)
    verify = next(i for i, s in enumerate(steps) if s.get("name") == "Verify checked-in vendor copies")
    recreate = next(i for i, s in enumerate(steps) if s.get("name") == "Recreate locked vendor files from GitHub")
    tests = [i for i, s in enumerate(steps) if "pytest " in s.get("run", "")]
    assert tests and verify < recreate < min(tests)
    original = next(
        s for s in ci["jobs"]["resolve-vendor"]["steps"]
        if s.get("name") == "Recreate locked vendor files from GitHub"
    )
    assert steps[recreate] == original
    tool = next(s for s in steps if s.get("name") == "Fetch pinned shared vendor tool")
    assert tool["with"]["ref"] == PIN
    for step in steps:
        assert "continue-on-error" not in step
        if step.get("uses", "").startswith("actions/checkout@"):
            assert step["with"]["persist-credentials"] == "false"
        if step.get("uses", "").startswith("actions/upload-artifact@"):
            assert step["with"]["name"].startswith("locked-")
            if step["with"]["name"].startswith(("locked-vendor-", "locked-junit-", "locked-controlled-")):
                assert step["if"] == "always()"
            assert step["with"]["if-no-files-found"] == "error"
    lock = next(s for s in steps if s.get("name") == "Preserve vendor lock used by this run")
    assert lock["with"]["path"] == "build/vendor-evidence-locked"


@pytest.mark.parametrize("job_name", ["resolve-vendor", "tooling", "vendor-locked"])
def test_pinned_parent_staging_command_and_real_payload(tmp_path, job_name):
    """Execute the workflow staging command against real lock bytes."""
    parent_tool = ROOT / ".vendor-sync-tools/vendor_stage.py"
    if not parent_tool.is_file():
        pytest.skip("pinned parent checkout is supplied by CI (ci.yml)")
    assert not (ROOT / "tools/stage_vendor_evidence.py").exists()
    _copy_snapshot(tmp_path)
    steps = _workflow()["jobs"][job_name]["steps"]
    staging = next(step for step in steps if step.get("name") == "Stage canonical vendor evidence")
    assert staging["if"] == "always()"
    command = staging["run"].replace(
        ".vendor-sync-tools/vendor_stage.py", shlex.quote(str(parent_tool))
    ).replace("python -S ", shlex.quote(sys.executable) + " -S ")
    syntax = subprocess.run(["bash", "-n"], input=command, text=True, capture_output=True)
    assert syntax.returncode == 0, syntax.stderr
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", command],
        cwd=tmp_path,
        env=os.environ,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    output = Path(json.loads(result.stdout)["output"])
    evidence = json.loads((output / "vendor-evidence.json").read_text(encoding="utf-8"))
    lock_members = {"vendor.lock.json", *[entry["destination"] for entry in _lock_entries(tmp_path)]}
    assert set(evidence["locked"]) == set(evidence["candidate"]) == lock_members
    assert evidence["kind"] == "locked"
    assert evidence["legacy"] == []
    assert evidence["runtime"] == []
    members = lock_members
    assert set(evidence["sha256"]) == members
    assert {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()} == members | {
        "vendor-evidence.json"
    }
    for member in members:
        data = (output / member).read_bytes()
        assert data == (tmp_path / member).read_bytes()
        assert hashlib.sha256(data).hexdigest() == evidence["sha256"][member]


def test_retired_ironmate_sources_do_not_follow_deleted_main_paths():
    entries = [e for e in _lock_entries() if e["repository"] == "myon-bioinformatics/Ironmate"]
    assert {e["source"] for e in entries} == {"LICENSE"}
    assert all(e["ref"] == e["commit"] for e in entries)


# ═══ 🔒 vendor lock ═══════════════════════════════════════════════════════════════════════════════════════

def test_vendor_lock_matches_checked_in_bytes() -> None:
    lock = json.loads((ROOT / "vendor.lock.json").read_text(encoding="utf-8"))
    assert lock["schema"] == "vendor-lock/1"
    for entry in lock["files"]:
        assert re.fullmatch(r"[0-9a-f]{40}", entry["ref"]), entry["destination"]
        assert entry["ref"] == entry["commit"], entry["destination"]
        data = (ROOT / entry["destination"]).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        assert blob == entry["blob_sha"], entry["destination"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["destination"]
