#!/usr/bin/env python3
"""Native Windows Git Bash / Compose configuration probe, NOT a database test.

Usage: python windows_probe.py --kit PATH --output-dir PATH

Requires Windows, Git for Windows, Python, and the real Docker Compose CLI.
Does not install software, start containers, pull images, or modify the kit.
The two stdin tests deliberately replace Docker with a Python argument/input
recorder; they establish shell handling only, not Docker or database behavior.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import ntpath
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import traceback


SCOPE = {
    "tested": [
        "native Windows Git-for-Windows Bash identification",
        "real Docker Compose parsing and path resolution in a folder with spaces",
        "CRLF Compose and seed-file handling at the shell/configuration boundary",
        "exact README seed-command arguments and raw stdin delivered to a Python recorder",
    ],
    "not_tested": [
        "Docker Desktop installation or startup",
        "Linux container creation, seed execution, database queries, or persistence",
        "Windows-to-Linux-VM bind-mount contents at runtime",
        "interactive Git Bash / MinTTY database-client behavior",
        "Apple Silicon or Windows ARM unless the recorded host actually has that architecture",
    ],
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find_git_bash(explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / "Git/bin/bash.exe")
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"]) / "Programs/Git/bin/bash.exe")
    git = shutil.which("git")
    if git:
        candidates.append(Path(git).resolve().parent.parent / "bin/bash.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("Native Git-for-Windows bash.exe not found; supply --bash PATH. WSL Bash is not a substitute.")


def prepare_kit(source: Path, destination: Path) -> list[dict]:
    """Copy only teaching inputs, never a .git directory or previous test output."""
    require(not destination.exists(), f"Refusing to overwrite existing copied kit: {destination}")
    required = [Path("compose.yaml"), Path("redis_seed.txt"), Path("mongo_seed/01_restaurants.js")]
    for relative in required:
        require((source / relative).is_file(), f"Missing kit input: {relative}")
    destination.mkdir(parents=True)
    records = []
    for relative in required:
        original = (source / relative).read_bytes()
        normalized = original.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        crlf = normalized.replace(b"\n", b"\r\n")
        require(b"\r\n" in crlf, f"Expected a multiline teaching input: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(crlf)
        require(b"\n" not in crlf.replace(b"\r\n", b""), f"Bare LF remains: {relative}")
        records.append({"file": relative.as_posix(), "original_sha256": digest(original),
                        "copied_sha256": digest(crlf), "bytes": len(crlf),
                        "crlf_count": crlf.count(b"\r\n"), "forced_crlf": True})
    if (source / "README.md").is_file():
        shutil.copy2(source / "README.md", destination / "README.md")
    return records


def validate_config(config: dict, staged_kit: Path) -> dict:
    require(set(config.get("services", {})) == {"mongo", "redis"}, "Expected exactly mongo and redis")
    require(config.get("networks", {}).get("default", {}).get("internal") is True,
            "Default network must remain internal")
    for name, service in config["services"].items():
        require(not service.get("ports"), f"Unexpected host ports on {name}")
        require("@sha256:" in service.get("image", ""), f"Image is not digest-pinned: {name}")
        require("127.0.0.1" in service.get("command", []), f"Loopback binding lost: {name}")
        require(bool(service.get("healthcheck", {}).get("test")), f"Health check lost: {name}")
    mongo_mounts = config["services"]["mongo"].get("volumes", [])
    redis_mounts = config["services"]["redis"].get("volumes", [])
    require(len(mongo_mounts) == 2 and len(redis_mounts) == 1, "Unexpected number of mounts")
    binds = [mount for mount in mongo_mounts if mount.get("type") == "bind"]
    require(len(binds) == 1, "Expected exactly one Mongo seed bind mount")
    mount = binds[0]
    require(mount.get("target") == "/docker-entrypoint-initdb.d", "Container seed path was changed")
    require(mount.get("read_only") is True, "Seed bind must remain read-only")
    expected_source = str(staged_kit / "mongo_seed")
    actual_source = mount.get("source", "")
    require(ntpath.isabs(actual_source), f"Bind source is not an absolute Windows path: {actual_source}")
    require(ntpath.normcase(ntpath.normpath(actual_source)) ==
            ntpath.normcase(ntpath.normpath(expected_source)),
            f"Wrong host bind source: {actual_source!r}; expected {expected_source!r}")
    require(" " in actual_source, "The bind source did not exercise a path with spaces")
    mongo_data = [item for item in mongo_mounts if item.get("type") == "volume"]
    require(len(mongo_data) == 1 and mongo_data[0].get("target") == "/data/db",
            "Mongo named volume/container path changed")
    require(redis_mounts[0].get("type") == "volume" and redis_mounts[0].get("target") == "/data",
            "Redis named volume/container path changed")
    return {"services": ["mongo", "redis"], "no_published_ports": True,
            "internal_network": True, "digest_pinned_images": True,
            "seed_bind_source": actual_source, "seed_bind_target": mount["target"],
            "seed_bind_read_only": True, "container_data_targets": ["/data/db", "/data"],
            "runtime_mount_verified": False}


def record_command(arguments: list[str]) -> None:
    # Explicit binary mode prevents this test helper from hiding CRLF conversion.
    if os.name == "nt":
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    data = sys.stdin.buffer.read()
    print(json.dumps({"kind": "python_argv_stdin_recorder_not_docker",
                      "argv": ["docker", *arguments],
                      "stdin_base64": base64.b64encode(data).decode("ascii"),
                      "stdin_bytes": len(data), "stdin_sha256": digest(data)}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kit", type=Path, required=True, help="Unmodified source kit containing compose.yaml")
    parser.add_argument("--output-dir", type=Path, required=True, help="New report/staging directory")
    parser.add_argument("--bash", help="Optional explicit path to native Git-for-Windows bash.exe")
    args = parser.parse_args()
    kit = args.kit.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "windows_probe_report.json"
    require(not report_path.exists(), f"Refusing to replace existing report: {report_path}")
    staged = output / "NoSQL Practice With Spaces"
    transcript = []
    report = {"status": "running", "scope": SCOPE, "started_utc": datetime.now(timezone.utc).isoformat(),
              "host": {"os_name": os.name, "platform": platform.platform(), "machine": platform.machine(),
                       "python": sys.version, "python_executable": sys.executable},
              "source_kit": str(kit), "copied_kit": str(staged), "checks": [],
              "database_end_to_end_tested": False, "containers_started_by_probe": False}
    try:
        require(os.name == "nt", "This probe must run on native Windows, not macOS, Linux, or WSL Python")
        bash = find_git_bash(args.bash)
        report["bash_executable"] = str(bash)
        report["copied_inputs"] = prepare_kit(kit, staged)
        env = os.environ.copy()
        env["PROBE_PYTHON"] = Path(sys.executable).as_posix()
        env["PROBE_SCRIPT"] = Path(__file__).resolve().as_posix()

        def run_bash(label: str, script: str, *, required: bool = True, timeout: int = 45) -> subprocess.CompletedProcess:
            command = [str(bash), "--noprofile", "--norc", "-c", "set -euo pipefail\n" + script]
            try:
                result = subprocess.run(command, cwd=staged, env=env, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            except subprocess.TimeoutExpired as error:
                if required:
                    raise
                result = subprocess.CompletedProcess(command, 124, error.stdout or b"",
                                                     (error.stderr or b"") + b"\nCapability query timed out.")
            record = {"label": label, "script": script, "returncode": result.returncode,
                      "stdout": result.stdout.decode("utf-8", errors="replace"),
                      "stderr": result.stderr.decode("utf-8", errors="replace")}
            transcript.append(record)
            if required:
                require(result.returncode == 0, f"{label} failed ({result.returncode}): {record['stderr']}")
            return result

        shell = run_bash("native_shell_identity", 'uname -s\nprintf "%s\\n" "$BASH_VERSION"\ncommand -v docker\ncygpath -w "$(command -v docker)"')
        identity = shell.stdout.decode("utf-8").splitlines()
        require(identity and identity[0].startswith(("MINGW", "MSYS")), "Not native Git-for-Windows Bash")
        docker_path = Path(identity[-1])
        # MSYS command lookup can omit .exe even though it launches that file.
        if docker_path.suffix.lower() != ".exe":
            docker_path = Path(str(docker_path) + ".exe")
        require(docker_path.name.lower() == "docker.exe" and docker_path.is_file(),
                "Resolved Docker is not the native Windows docker.exe")
        report["docker_executable"] = str(docker_path)
        report["shell_identity"] = identity
        report["checks"].append("native_git_bash_and_windows_docker_client")
        run_bash("docker_client_version", "docker --version")
        run_bash("compose_plugin_version", "docker compose version")

        config_result = run_bash("real_compose_config_crlf_path_with_spaces", "docker compose config --format json")
        config = json.loads(config_result.stdout.decode("utf-8-sig"))
        write_json(output / "compose_config.json", config)
        report["config_assertions"] = validate_config(config, staged)
        report["checks"].append("real_compose_config_with_crlf_and_space_paths")

        info_template = ('{"OSType":{{json .OSType}},"Architecture":{{json .Architecture}},'
                         '"OperatingSystem":{{json .OperatingSystem}},"ServerVersion":{{json .ServerVersion}}}')
        info = run_bash("docker_daemon_capability_only", "docker info --format '" + info_template + "'", required=False)
        report["docker_capability"] = {"reachable": info.returncode == 0,
                                       "services_started": False, "database_execution_attempted": False}
        if info.returncode == 0:
            report["docker_capability"]["server"] = json.loads(info.stdout.decode("utf-8-sig"))
        else:
            report["docker_capability"]["note"] = "Daemon not reachable; this is not a failure of the shell/configuration probe."

        for name, relative, student_command, expected_argv in [
            ("redis_seed", "redis_seed.txt", "docker compose exec -T redis redis-cli < redis_seed.txt",
             ["docker", "compose", "exec", "-T", "redis", "redis-cli"]),
            ("mongo_reset", "mongo_seed/01_restaurants.js", "docker compose exec -T mongo mongosh --quiet < mongo_seed/01_restaurants.js",
             ["docker", "compose", "exec", "-T", "mongo", "mongosh", "--quiet"]),
        ]:
            # Only these two calls shadow Docker. Real config/capability calls above do not.
            snippet = 'docker() { "$PROBE_PYTHON" "$PROBE_SCRIPT" --record-command "$@"; }\n' + student_command
            recorded = json.loads(run_bash(name + "_python_recorder_only", snippet).stdout.decode("utf-8-sig"))
            received = base64.b64decode(recorded.pop("stdin_base64"), validate=True)
            expected = (staged / relative).read_bytes()
            require(recorded["argv"] == expected_argv, f"Shell changed command arguments: {name}")
            require(received == expected, f"Shell/recorder changed redirected seed bytes: {name}")
            require(b"\r\n" in received, f"CRLF input was not exercised: {name}")
            report["checks"].append({"name": name, "student_command": student_command,
                                     "argv_and_bytes_preserved": True, "crlf_count": received.count(b"\r\n"),
                                     "recorder": recorded, "docker_or_database_executed": False})
        report["status"] = "passed_shell_path_stdin_and_config_only"
        return_code = 0
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        report["traceback"] = traceback.format_exc()
        return_code = 1
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(report_path, report)
        write_json(output / "windows_probe_transcript.json", transcript)
        print(json.dumps({"status": report["status"], "report": str(report_path),
                          "database_end_to_end_tested": False}, indent=2))
    return return_code


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--record-command":
        record_command(sys.argv[2:])
    else:
        raise SystemExit(main())
