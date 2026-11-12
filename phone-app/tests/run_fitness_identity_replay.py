"""Replay real recorder code while preserving the MiFitness identity boundary.

No production files are patched. Android/SDK classes use the existing host
boundary doubles. isWearAppInstalled(true), authorization and listener success
are explicit injected SDK outcomes, never a signature or firmware acceptance
test. The actual ARM sender's existing host_reset also injects an already-ready
transport; no commercial firmware instruction executes.

Full run joins actual ARM phone-link/export-relay -> actual Java PhoneLink /
WatchListenerLease -> actual Protocol/ArchiveStore -> actual PhoneLink.send ->
actual ARM ACK handling. Listener-to-protocol dispatch and Android directory
sync are test edges; ReceiverService, MiFitness, RF and Android are not run.
Only generated PCM in temporary directories is used. Optional identity evidence
verification reads the pinned local AP and region hashes, never executes it.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

PHONE = Path(__file__).resolve().parents[1]
ROOT = PHONE.parent
SCENARIOS = [
    "permission_before_sdk", "authorization_before_identity",
    "identity_missing_after_authorization", "identity_lookup_failure",
    "identity_true_listener_rejected", "ready_without_delivery_is_not_export",
    "wrong_peer_never_reaches_protocol",
]
ACTUAL_JAVA = [PHONE / "src/com/watch6/recorder" / name for name in (
    "PhoneLink.java", "WatchListenerLease.java", "Protocol.java", "ArchiveStore.java")]
ACTUAL_NATIVE = [ROOT / "native" / name for name in (
    "phone-link.c", "export-relay.c", "export-relay-fs.c", "export-relay-json.c")]


def require(value, reason):
    if not value:
        raise AssertionError(reason)


def compile_java(work):
    spec = importlib.util.spec_from_file_location("fitness_boundary", PHONE / "tests/run_fitness_host.py")
    boundary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boundary)
    private = PHONE / ".local-build.json"
    config = json.loads(private.read_text(encoding="utf-8-sig")) if private.is_file() else {}
    java = Path(os.environ.get("JAVA_HOME", config.get("java_home", "")))
    jar = Path(os.environ.get("W6R_JSON_TEST_JAR", config.get("json_test_jar", "")))
    require(jar.is_file(), "Configure authorized W6R_JSON_TEST_JAR for JVM replay")
    suffix = ".exe" if os.name == "nt" else ""
    files = []
    for name, code in boundary.STUBS.items():
        package, _ = name.rsplit(".", 1)
        target = work / (name.replace(".", "/") + ".java")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("package " + package + ";\n" + code, encoding="utf-8")
        files.append(target)
    files += ACTUAL_JAVA + [PHONE / "tests/FitnessIdentityReplayHostTest.java"]
    result = subprocess.run([str(java / ("bin/javac" + suffix)), "-encoding", "UTF-8",
        "-classpath", str(jar), "-d", str(work), *map(str, files)], capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=30)
    require(result.returncode == 0, result.stderr)
    return [str(java / ("bin/java" + suffix)), "-cp", os.pathsep.join([str(work), str(jar)]),
        "com.watch6.recorder.FitnessIdentityReplayHostTest"]


def phone(command, scenario, store, frame=None):
    text = None if frame is None else json.dumps({"sender": "watch-a", "frame": frame}) + "\n"
    result = subprocess.run([*command, scenario, str(store)], input=text, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=30)
    require(result.returncode == 0, scenario + "\n" + result.stderr)
    return json.loads(result.stdout)


def replay_native(command, work):
    sys.path.insert(0, str(ROOT / "tests"))
    import test_phone_transport as native
    native.TransportTests.setUpClass()
    cases = []
    try:
        for case in ("complete", "lost_ack_resume", "wrong_whole_crc"):
            h = native.Host(native.TransportTests.raw, native.TransportTests.sections, native.TransportTests.syms)
            h.setup(6000)
            if case == "wrong_whole_crc":
                h.files[native.BASE + b"w6r-export-job.txt"] = native.job(6000, crc="00000000")
            store = work / ("native-" + case)
            exchanges = []

            def exchange(deliver_ack=True):
                request = h.wire()
                result = phone(command, "frame", store, request)
                require(result["deliveries"] == 1 and result["protocol_calls"] == 1,
                    "actual PhoneLink must deliver exactly once into the real protocol")
                require(result["sdk_sends"] == 1 and len(result["sends"]) == 1,
                    "actual PhoneLink.send must issue exactly one SDK ACK")
                reply = result["sends"][0]
                require(result["diagnostics"]["rx_packets"] == 1 and result["diagnostics"]["tx_packets"] == 1,
                    "real PhoneLink counters must confirm both callback directions")
                require(reply["request_id"] == request["id"], "actual protocol ACK must match request")
                frontier = h.get(5)
                h.complete()
                require(h.get(5) == frontier, "native SDK send completion cannot advance durable audio")
                if deliver_ack:
                    h.receive(reply)
                exchanges.append(dict(action=request["action"], offset=request.get("offset"),
                    ok=reply["ok"], durable=reply["durable"], complete=reply["complete"],
                    ack_delivered_to_native=deliver_ack, phone_assertions=result["assertions"]))
                return reply

            h.tick(25)
            require(exchange()["next"] == 0, "offer must start from zero")
            h.tick(50)
            exchange()
            require(h.get(5) == 2048, "first native durable frontier")
            h.tick(75)
            if case == "lost_ack_resume":
                lost = exchange(False)
                require(lost["durable"] == 4096 and h.get(5) == 2048, "lost ACK cannot advance native state")
                h.call("host_event", 3)
                # Existing host_online bypasses the unavailable firmware route.
                # This tests export recovery after injected transport restoration.
                h.call("host_online")
                h.tick(100)
                require(h.wire()["action"] == "recorder_offer", "native reconnect must reoffer")
                require(exchange()["next"] == 4096 and h.get(5) == 4096, "real stored checkpoint must resume")
                stamp = 125
            else:
                exchange()
                stamp = 100
            h.tick(stamp)
            require(h.wire()["offset"] == 4096, "final chunk must continue exact native frontier")
            exchange()
            h.tick(stamp + 25)
            require(h.wire()["action"] == "recorder_finish", "real sender must finish after all durable chunks")
            reply = exchange()
            files = list(store.rglob("*.wav"))
            source = native.BASE + b"w6r-play-" + native.CACHE.encode() + b".wav"
            require(source in h.files, "watch source must remain present")
            if case == "wrong_whole_crc":
                require(not reply["ok"] and not reply["complete"] and h.get(4) == 6,
                    "real protocol rejection must make native exporter fail closed")
                require(not files and h.get(5) == 6000, "rejected final checksum cannot produce a saved WAV")
                cases.append(dict(scenario=case, exchanges=exchanges, native_phase="error",
                    watch_source_preserved=True, saved_wav_count=0))
            else:
                require(reply["ok"] and reply["complete"] and h.get(4) == 4,
                    "only real saved ACK completes native exporter")
                require(len(files) == 1, "one complete synthetic recording")
                data = files[0].read_bytes()
                require(data == native.wav(h.pcm), "saved PCM/WAV must equal the exact native source")
                require(reply["sha256"] == hashlib.sha256(data).hexdigest(), "saved ACK digest must match actual WAV")
                require(h.get(9) == 1, "native source descriptor must be closed")
                h.tick(stamp + 50)
                h.call("host_worker_closed")
                require(h.call("host_unload") == 0, "completed callbacks permit guarded unload")
                cases.append(dict(scenario=case, exchanges=exchanges, native_phase="saved", bytes=len(h.pcm),
                    wav_sha256=hashlib.sha256(data).hexdigest(), watch_source_preserved=True, saved_wav_count=1))
    finally:
        native.TransportTests.tearDownClass()
    return cases


def verify_static_evidence(path):
    sys.path.insert(0, str(ROOT))
    from build_settings import AP_SHA256, firmware_path
    evidence = json.loads(path.read_text(encoding="utf-8-sig"))
    raw = firmware_path("ap").read_bytes()
    require(hashlib.sha256(raw).hexdigest() == AP_SHA256 == evidence["ap_sha256"], "fixed AP hash mismatch")
    regions = evidence["regions"]
    required = {"send_wearmsg", "verify_phone_message", "get_appinfo", "installed_vector_lookup"}
    require(required <= {r["name"] for r in regions}, "identity evidence is incomplete")
    for region in regions:
        # Pinned AP load base, also used by tools/phone_link_profile.py.
        offset = int(region["address"], 0) - 0x0c0c0000
        require(0 <= offset <= len(raw) - region["bytes"], "identity region outside fixed AP")
        require(hashlib.sha256(raw[offset:offset + region["bytes"]]).hexdigest() == region["sha256"],
            "identity region hash mismatch: " + region["name"])
    return dict(status="matched", ap_sha256=AP_SHA256, regions=len(regions),
        regions_verified=[r["name"] for r in regions], firmware_executed=False,
        scope="hash consistency with existing static analysis; no protocol/identity execution")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only-sdk", action="store_true", help="omit existing native ARM host dependency")
    parser.add_argument("--identity-evidence", type=Path, help="optional already-authorized local static evidence JSON")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in ACTUAL_JAVA + ACTUAL_NATIVE}
    static = verify_static_evidence(args.identity_evidence) if args.identity_evidence else {"status": "not_requested"}
    with tempfile.TemporaryDirectory(prefix="w6r-fitness-identity-replay-") as directory:
        work = Path(directory)
        command = compile_java(work)
        sdk = [phone(command, scenario, work / scenario) for scenario in SCENARIOS]
        native = [] if args.only_sdk else replay_native(command, work)
    require(all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items()),
        "production sources changed during replay")
    report = dict(passed=True, sdk_cases=len(sdk), native_export_cases=len(native), sdk_scenarios=sdk,
        native_replays=native, static_identity_evidence=static,
        scope="real recorder code at injected SDK/OS boundaries; not a firmware identity or physical MiFitness test",
        actual_java=[p.name for p in ACTUAL_JAVA], actual_native=[] if args.only_sdk else [p.name for p in ACTUAL_NATIVE],
        sdk_callbacks_mocked=True, firmware_instructions_executed=False, firmware_identity_validated=False,
        native_transport_ready_injected=not args.only_sdk, sdk_identity_true_injected=True,
        real_signature_checked=False, receiver_service_executed=False, listener_protocol_dispatch="harness",
        directory_sync="injected JVM edge; actual file data/checkpoint sync and atomic moves execute",
        device_accessed=False, personal_audio_read=False, single_bin_mifitness_export_proven=False,
        production_unchanged=True,
        production_sha256={str(p.relative_to(ROOT)).replace("\\", "/"): digest for p, digest in before.items()})
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
