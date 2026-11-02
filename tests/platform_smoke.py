"""Isolated NoSQL kit validation; Python standard library, Bash, Docker only.

Run on the actual target host. Does not install or reconfigure Docker, bypass
Redis guards, publish ports, edit the input kit, or remove volumes. Cleanup
stops/removes only containers and networks in this run's unique Compose project.
The exact query checks are noninteractive; this is not an interactive PTY test.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
import traceback
import uuid


def normalize(value):
    """Only line-ending normalization is permitted for query output equality."""
    return value.replace("\r\n", "\n")


def architecture(value):
    return {"aarch64": "arm64", "ARM64": "arm64", "x86_64": "amd64",
            "x64": "amd64", "AMD64": "amd64"}.get(value, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-arch", choices=("arm64", "amd64"), required=True)
    args = parser.parse_args()
    kit, output = args.kit.resolve(), args.output_dir.resolve()
    fixture_path = args.fixtures.resolve()
    fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))
    cases = fixtures["cases"]
    if len(cases) != 17 or len({c["id"] for c in cases}) != 17:
        parser.error("The fixture must contain exactly 17 unique query cases.")
    output.mkdir(parents=True, exist_ok=True)
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    project = "stat315-platform-" + run_id.lower()
    work = output / ("practice path with spaces " + run_id)
    report = {"schema_version": 1, "run_id": run_id, "project": project,
              "status": "RUNNING", "expected_arch": args.expected_arch,
              "kit_source": str(kit), "working_copy": str(work),
              "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
              "host": {"system": platform.system(), "machine": platform.machine(),
                       "platform": platform.platform(), "python": sys.version},
              "events": [], "checks": [], "query_results": [],
              "limitations": ["Batch CLI tests do not establish interactive terminal behavior.",
                              "Native Linux ARM64 is not a native macOS Apple Silicon test.",
                              "Windows is not validated unless this program actually runs there."]}

    def save():
        (output / "platform_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        lines = ["STAT315 NoSQL platform validation", "Status: " + report["status"],
                 "Project: " + project, "Host: " + json.dumps(report["host"]), ""]
        for event in report["events"]:
            lines += ["[" + event["label"] + "]", "$ " + shlex.join(event["argv"]),
                      "cwd: " + event["cwd"], "exit: " + str(event["returncode"]),
                      "STDOUT:", event["stdout"], "STDERR:", event["stderr"], ""]
        lines += ["CHECKS"] + [("PASS " if c["pass"] else "FAIL ") + c["label"] for c in report["checks"]]
        (output / "platform_transcript.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run(argv, label, cwd=None, timeout=120, required=True):
        argv = [str(x) for x in argv]
        start = time.monotonic()
        try:
            result = subprocess.run(argv, cwd=cwd or work, capture_output=True, timeout=timeout)
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, code = exc.stdout or b"", (exc.stderr or b"") + b"\nCOMMAND TIMED OUT", 124
        event = {"label": label, "argv": argv, "cwd": str(cwd or work), "returncode": code,
                 "stdout": stdout.decode("utf-8", errors="replace"),
                 "stderr": stderr.decode("utf-8", errors="replace"),
                 "elapsed_seconds": round(time.monotonic() - start, 3)}
        report["events"].append(event)
        print(f"{label}: exit {code}", flush=True)
        save()
        if required and code:
            raise RuntimeError(label + ": " + event["stderr"] + event["stdout"])
        return event

    def check(label, condition, details=None):
        report["checks"].append({"label": label, "pass": bool(condition), "details": details})
        save()
        if not condition:
            raise AssertionError(label)

    compose = ["docker", "compose", "--project-name", project, "--file", "compose.yaml"]

    def bash(argv, label, redirect=None, **kwargs):
        command = shlex.join([str(x) for x in argv])
        if redirect:
            command += " < " + shlex.quote(redirect)
        return run(["bash", "-c", command], label, **kwargs)

    def mongo(code, label):
        return bash(compose + ["exec", "-T", "mongo", "mongosh", "--quiet", "stat315_nosql", "--eval", code], label)

    def redis(code, label):
        return bash(compose + ["exec", "-T", "redis", "redis-cli", "--raw"] + shlex.split(code), label)

    def reset(label):
        bash(compose + ["exec", "-T", "mongo", "mongosh", "--quiet"], label + " Mongo stdin reset",
             redirect="mongo_seed/01_restaurants.js")
        bash(compose + ["exec", "-T", "redis", "redis-cli"], label + " Redis stdin reset", redirect="redis_seed.txt")

    def snapshot(label):
        return {"mongo": normalize(mongo("JSON.stringify(db.restaurants.find().sort({_id:1}).toArray())", label + " Mongo snapshot")["stdout"]),
                "leaderboard": normalize(redis("ZRANGE stat315:leaderboard 0 -1 WITHSCORES", label + " Redis scores")["stdout"]),
                "announcement": normalize(redis("GET stat315:announcement", label + " Redis announcement")["stdout"]),
                "names": [normalize(redis(f"HGET stat315:player:{p} name", label + f" Redis name {p}")["stdout"])
                          for p in (100, 101, 102, 103)]}

    def existing_state(ids, label):
        if not ids:
            return {}
        containers = json.loads(run(["docker", "inspect", *ids], label)["stdout"])
        return {c["Id"]: {"name": c["Name"], "status": c["State"]["Status"],
                           "started": c["State"]["StartedAt"]} for c in containers}

    owned = False
    originals = None
    try:
        work.mkdir()
        files = ("compose.yaml", "redis_seed.txt", "mongo_seed/01_restaurants.js")
        report["kit_sha256"] = {}
        for name in files:
            src, dst = kit / name, work / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            report["kit_sha256"][name] = hashlib.sha256(src.read_bytes()).hexdigest()
        check("working copy path contains spaces", " " in str(work))
        check("host CPU matches requested architecture", architecture(platform.machine()) == args.expected_arch)
        run(["bash", "--version"], "Bash version")
        report["bash_uname"] = run(["bash", "-c", "uname -srm"], "Bash host identity")["stdout"]
        docker = json.loads(run(["docker", "version", "--format", "{{json .}}"], "Docker client and engine versions")["stdout"])
        report["docker"] = docker
        check("Docker engine is Linux", docker["Server"]["Os"] == "linux")
        check("Docker engine CPU matches requested architecture", architecture(docker["Server"]["Arch"]) == args.expected_arch)
        report["execution_label"] = ("native Linux " + args.expected_arch if platform.system() == "Linux"
                                     else platform.system() + " host with Linux " + args.expected_arch + " containers")
        report["compose_version"] = run(["docker", "compose", "version"], "Compose version")["stdout"]
        config = json.loads(bash(compose + ["config", "--format", "json"], "Resolve exact kit Compose config")["stdout"])
        check("kit has only Mongo and Redis services", set(config["services"]) == {"mongo", "redis"})
        check("kit declares no published ports", all(not s.get("ports") for s in config["services"].values()))
        check("kit images are digest pinned", all("@sha256:" in s["image"] for s in config["services"].values()))
        original_ids = run(["docker", "ps", "-aq"], "Original container IDs")["stdout"].split()
        originals = existing_state(original_ids, "Original container states")
        for kind, cmd in (("containers", ["docker", "ps", "-aq"]), ("volumes", ["docker", "volume", "ls", "-q"]),
                          ("networks", ["docker", "network", "ls", "-q"])):
            found = run(cmd + ["--filter", "label=com.docker.compose.project=" + project], "Check unused project " + kind)["stdout"].strip()
            check("no preexisting project " + kind, not found)
        owned = True
        bash(compose + ["up", "--detach", "--wait", "--wait-timeout", "240"], "Start isolated kit", timeout=480)
        ids = bash(compose + ["ps", "-q"], "Started container IDs")["stdout"].split()
        containers = json.loads(run(["docker", "inspect", *ids], "Inspect started containers")["stdout"])
        check("both services healthy", len(containers) == 2 and all(c["State"].get("Health", {}).get("Status") == "healthy" for c in containers))
        check("no host port bindings", all(not c["HostConfig"].get("PortBindings") for c in containers))
        networks = sorted({n["NetworkID"] for c in containers for n in c["NetworkSettings"]["Networks"].values()})
        network_data = json.loads(run(["docker", "network", "inspect", *networks], "Inspect network isolation")["stdout"])
        check("all attached networks internal and scoped to this project", bool(network_data) and all(n["Internal"] and n["Labels"].get("com.docker.compose.project") == project for n in network_data))
        image_ids = sorted({c["Image"] for c in containers})
        images = json.loads(run(["docker", "image", "inspect", *image_ids], "Inspect executed image architectures")["stdout"])
        report["executed_images"] = [{"id": i["Id"], "architecture": i["Architecture"], "os": i["Os"], "digests": i.get("RepoDigests", [])} for i in images]
        check("both actual images are requested native architecture", len(images) == 2 and all(i["Architecture"] == args.expected_arch and i["Os"] == "linux" for i in images))
        report["mounted_volumes"] = sorted({m["Name"] for c in containers for m in c["Mounts"] if m["Type"] == "volume"})
        check("automatic Mongo seed is eight documents", normalize(mongo("db.restaurants.countDocuments()", "Automatic first-start seed")["stdout"]) == "8\n")
        allocator = json.loads(mongo("JSON.stringify(db.getSiblingDB('admin').serverStatus().tcmalloc.usingPerCPUCaches)", "Allocator cache mode")["stdout"])
        check("MongoDB uses per-thread allocator caches", allocator is False)
        workload = json.loads(mongo("""
const probe = db.getCollection("__kernel_compat_probe");
const started = Date.now();
let rounds = 0;
try {
  while (Date.now() - started < 90000) {
    probe.updateOne({_id: "probe"}, {$set: {round: rounds}}, {upsert: true});
    if (probe.findOne({_id: "probe"}).round !== rounds)
      throw new Error("Workload read-after-write mismatch");
    if (db.restaurants.countDocuments() !== 8)
      throw new Error("Practice seed changed during workload");
    rounds++;
    sleep(100);
  }
  const status = db.getSiblingDB("admin").serverStatus();
  print(JSON.stringify({
    durationMs: Date.now() - started,
    rounds: rounds,
    usingPerCPUCaches: status.tcmalloc.usingPerCPUCaches,
    uptime: status.uptime
  }));
} finally {
  probe.drop();
}
""", "90-second Mongo read/write workload")["stdout"])
        report["kernel_compatibility_workload"] = workload
        check("Mongo read/write workload completes beyond 90 seconds", workload["durationMs"] >= 90000 and workload["rounds"] > 0 and workload["uptime"] >= 90)
        check("per-thread allocator remains active after workload", workload["usingPerCPUCaches"] is False)
        reset("First")
        initial = snapshot("Initial")
        reset("Repeated")
        check("stdin resets are idempotent", snapshot("Repeated") == initial)
        for case in cases:
            event = (mongo if case["engine"] == "mongo" else redis)(case["code"], "Query " + case["id"])
            passed = normalize(event["stdout"]) == normalize(case["expected_stdout"])
            report["query_results"].append({**case, "stdout": event["stdout"], "stderr": event["stderr"],
                                             "returncode": event["returncode"], "pass": passed})
            check("exact query stdout: " + case["id"], passed)
        updated = snapshot("Updated")
        check("Mongo and Redis updates both change data", initial["mongo"] != updated["mongo"] and initial["leaderboard"] != updated["leaderboard"])
        bash(compose + ["up", "--detach", "--force-recreate", "--wait", "--wait-timeout", "180"], "Recreate containers with retained volumes", timeout=240)
        check("updates persist through container recreation", snapshot("After recreation") == updated)
        reset("Restore after updates")
        check("reset restores original seeded state", snapshot("Restored") == initial)
        # Replay Windows-style seed bytes only in this disposable working copy.
        for name in ("redis_seed.txt", "mongo_seed/01_restaurants.js"):
            path = work / name
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        reset("CRLF file")
        check("CRLF seed inputs preserve exact original data", snapshot("CRLF") == initial)
        check("input kit files were not modified", all(hashlib.sha256((kit / name).read_bytes()).hexdigest() == digest for name, digest in report["kit_sha256"].items()))
        report["status"] = "PASS"
    except Exception:
        report["status"] = "FAIL"
        report["error"] = traceback.format_exc()
        print(report["error"], file=sys.stderr)
    finally:
        if owned:
            bash(compose + ["logs", "--no-color"], "Final test-project logs", required=False)
            cleanup = bash(compose + ["down", "--timeout", "10"], "Stop only test-project containers; retain volumes", required=False)
            if cleanup["returncode"]:
                report["status"] = "FAIL"
            report["retained_volumes"] = run(["docker", "volume", "ls", "-q", "--filter", "label=com.docker.compose.project=" + project], "Retained test volume names", required=False)["stdout"].split()
        if originals is not None:
            try:
                check("original containers retain state and start time", existing_state(list(originals), "Original containers after tests") == originals)
            except Exception:
                report["status"] = "FAIL"
                report["cleanup_error"] = traceback.format_exc()
        save()
    print(report["status"] + ": " + str(output / "platform_report.json"), flush=True)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

