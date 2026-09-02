"""In-container fixture bootstrap and sentinel probe; standard library only."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

MAX_INPUT = 196_608


def _read_cgroup(name: str) -> str:
    path = Path("/sys/fs/cgroup") / name
    return path.read_text(encoding="ascii").strip() if path.exists() else "missing"


def _metadata_blocked() -> bool:
    connection = socket.socket()
    connection.settimeout(0.2)
    try:
        return connection.connect_ex(("169.254.169.254", 80)) != 0
    finally:
        connection.close()


def _root_read_only() -> bool:
    target = Path("/opt/releaseproof-write-probe")
    try:
        target.write_text("blocked", encoding="ascii")
    except OSError:
        return True
    target.unlink(missing_ok=True)
    return False


def _checks(plan: dict[str, object]) -> dict[str, bool]:
    limits = plan["resources"]
    assert isinstance(limits, dict)
    cpu = _read_cgroup("cpu.max").split()
    cpu_allowed = cpu[0] != "max" and int(cpu[0]) * 1000 // int(cpu[1]) <= int(limits["cpu_millis"])
    interfaces = Path("/proc/net/dev").read_text(encoding="ascii").splitlines()[2:]
    names = {line.split(":", maxsplit=1)[0].strip() for line in interfaces}
    workspace_capacity = os.statvfs("/workspace").f_frsize * os.statvfs("/workspace").f_blocks
    status = Path("/proc/self/status").read_text(encoding="ascii")
    return {
        "capabilities_dropped": "CapEff:\t0000000000000000" in status,
        "cpu_bounded": cpu_allowed,
        "docker_socket_absent": not Path("/var/run/docker.sock").exists(),
        "host_mount_absent": not Path("/host").exists(),
        "memory_bounded": _read_cgroup("memory.max") == str(limits["memory_bytes"]),
        "metadata_blocked": _metadata_blocked(),
        "network_loopback_only": names <= {"lo"},
        "no_new_privileges": "NoNewPrivs:\t1" in status,
        "non_root": os.getuid() == 65532 and os.getgid() == 65532,
        "pids_bounded": _read_cgroup("pids.max") == str(limits["pids"]),
        "root_read_only": _root_read_only(),
        "sentinel_secret_absent": "RELEASEPROOF_HOST_SENTINEL" not in os.environ,
        "writable_disk_bounded": workspace_capacity <= int(limits["writable_tmpfs_bytes"]),
    }


def _content_from_patch(file_path: str, patch: str) -> str:
    lines = patch.splitlines()
    if len(lines) < 3 or lines[0] != "--- /dev/null" or lines[1] != f"+++ b/{file_path}":
        raise ValueError("patch header invalid")
    content: list[str] = []
    seen_hunk = False
    for line in lines[2:]:
        if not seen_hunk:
            if not line.startswith("@@ -0,0 +1,"):
                raise ValueError("patch hunk invalid")
            seen_hunk = True
        elif line.startswith("+") and not line.startswith("+++"):
            content.append(line[1:])
        else:
            raise ValueError("patch is not add-only")
    if not seen_hunk:
        raise ValueError("patch hunk missing")
    return "\n".join(content) + "\n"


def _capture(path: Path, limit: int) -> dict[str, object]:
    size = path.stat().st_size
    digest = hashlib.sha256()
    excerpt = bytearray()
    with path.open("rb") as stream:
        while chunk := stream.read(65_536):
            digest.update(chunk)
            if len(excerpt) < limit:
                excerpt.extend(chunk[: limit - len(excerpt)])
    return {
        "excerpt": bytes(excerpt).decode("utf-8", errors="replace"),
        "original_bytes": size,
        "sha256": digest.hexdigest(),
        "truncated": size > limit,
    }


def _resolved_allowlisted_command(command: object, file_path: str) -> list[str]:
    expected = ["python", "-m", "pytest", "-q", file_path]
    if command != expected:
        raise ValueError("command is not allowlisted")
    return [sys.executable, *expected[1:]]


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        return 64
    payload = json.loads(raw)
    plan = payload["plan"]
    execution_input = payload["input"]
    limits = plan["resources"]
    checks = _checks(plan)
    started = time.monotonic()
    outcome = "isolation_failure"
    exit_code: int | None = None
    timed_out = False
    killed = False
    stdout_path = Path("/workspace/stdout.bin")
    stderr_path = Path("/workspace/stderr.bin")
    stdout_path.touch()
    stderr_path.touch()
    if all(checks.values()):
        shutil.copytree("/opt/fixture/repository", "/workspace/repository")
        target = Path("/workspace/repository") / execution_input["file_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            _content_from_patch(execution_input["file_path"], execution_input["patch"]),
            encoding="utf-8",
        )
        environment = dict(plan["environment"])
        environment["PYTHONPATH"] = "/workspace/repository/src"
        command = _resolved_allowlisted_command(plan["commands"][0], execution_input["file_path"])
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(  # noqa: S603
                command,
                cwd="/workspace/repository",
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
            )
            try:
                exit_code = process.wait(timeout=int(limits["wall_time_seconds"]))
                outcome = "passed" if exit_code == 0 else "failed"
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                outcome = "timeout"
                timed_out = True
                killed = True
    result = {
        "artifacts": ["runner-result-json-v1"],
        "attempt": payload["attempt"],
        "cleanup_succeeded": False,
        "elapsed_milliseconds": int((time.monotonic() - started) * 1000),
        "exit_code": exit_code,
        "image": plan["image"],
        "isolation_checks": checks,
        "killed": killed,
        "outcome": outcome,
        "plan_sha256": plan["plan_sha256"],
        "runner_version": "releaseproof-fixture-runner-v1",
        "schema_version": "releaseproof.execution-result.v1",
        "stderr": _capture(stderr_path, int(limits["output_bytes"])),
        "stdout": _capture(stdout_path, int(limits["output_bytes"])),
        "timed_out": timed_out,
    }
    canonical = json.dumps(
        result, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    result["result_sha256"] = hashlib.sha256(canonical.encode("ascii")).hexdigest()
    sys.stdout.write(
        json.dumps(
            result, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
