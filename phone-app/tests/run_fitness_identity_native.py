"""Opt-in fixed-P65 identity-branch replay using actual AP instructions.

Default invocation does not read a private AP or require Unicorn. Explicitly use
--execute-private-ap to execute two pinned Thumb routines with synthetic inputs:
  verify_phone_message(package, fingerprint, payload, length), and
  send_wearmsg(package, payload, length).

The actual 20-byte comparison and rejection/dispatch branches execute unchanged.
quickapp_get_appinfo is a dependency hook with its observed 0/-1 return and
output+0x10 fingerprint-pointer ABI. This does not execute PackageManager or
register any identity. Logging, libc operations and terminal dispatch calls are
also exact-address hooks. Reaching dispatch is not physical MiFitness delivery.
No device, private signer, real recordings, firmware writes or production edits.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
AP_BASE = 0x0c0c0000
AP_SHA256 = "a19b601477569765103eaf468b937bd8026b4d68ffa5c896bde222a79e475858"
VERIFY = 0x0c82e588
SEND = 0x0c830a88
WINDOWS = [
    ("verify_phone_message", VERIFY, 140, "f8ad83497194b8be641b5fa23d034906b353dbdb1e637c92ee74966412cf5bc5"),
    ("send_wearmsg", SEND, 184, "36874414ecdf5c4d85740d52c17f70a6f4cebcab65b0448cd3fb3f8ee5484f0d"),
]
# These code boundaries exclude the following literal pools. Literal bytes are
# nevertheless guarded by the full AP hash; no disassembled literal is run.
CODE_RANGES = [(VERIFY, 0x0c82e614), (SEND, 0x0c830b2c)]
GET_APPINFO = 0x0c82cf5c
LOG = 0x0c504a54
MEMSET = 0x0c8be820
MEMCPY = 0x0c8be398
MALLOC = 0x0c50b2a0
FREE = 0x0c50b25c
RX_DISPATCH = 0x0c82e1ec
TX_DISPATCH = 0x0ca40064
HOOKS = {GET_APPINFO: "quickapp_get_appinfo", LOG: "log", MEMSET: "memset",
    MEMCPY: "memcpy", MALLOC: "malloc", FREE: "free",
    RX_DISPATCH: "quickapp_proxy_server_send_edge", TX_DISPATCH: "packet_send_edge"}
RAM = 0x20000000
PACKAGE = RAM
LOCAL_FP = RAM + 0x100
INPUT_FP = RAM + 0x200
PAYLOAD = RAM + 0x300
HEAP = RAM + 0x8000
STACK = RAM + 0x1f000
STOP = RAM + 0x1fff0
GLOBAL_APPINFO = 0x3c45abbc  # Literal loaded at verify+4, not a guessed C++ layout.
SYNTHETIC_PACKAGE = b"com.watch6.recorder\0"
SYNTHETIC_FP = bytes(range(0x30, 0x44))
SYNTHETIC_PAYLOAD = b'{"protocol":"w6r1","synthetic":true}'


def require(condition, reason):
    if not condition:
        raise AssertionError(reason)


def load_runtime():
    sys.path.insert(0, str(ROOT))
    from build_settings import configuration, prepare_python_dependencies
    prepare_python_dependencies()
    dependencies = configuration().get("test_dependencies")
    if dependencies:
        sys.path.insert(0, str(dependencies))
    import unicorn
    from unicorn import arm_const
    return unicorn, arm_const


class Replay:
    def __init__(self, raw, uc, regs, installed):
        self.uc, self.regs, self.installed = uc, regs, installed
        self.u = uc.Uc(uc.UC_ARCH_ARM, uc.UC_MODE_THUMB | uc.UC_MODE_MCLASS)
        self.ap_size = (len(raw) + 4095) & ~4095
        self.u.mem_map(AP_BASE, self.ap_size)
        self.u.mem_write(AP_BASE, raw)
        self.u.mem_protect(AP_BASE, self.ap_size, uc.UC_PROT_READ | uc.UC_PROT_EXEC)
        self.u.mem_map(RAM, 0x20000)
        self.u.mem_map(0x3c450000, 0x10000)
        self.u.mem_write(PACKAGE, SYNTHETIC_PACKAGE)
        self.u.mem_write(LOCAL_FP, SYNTHETIC_FP)
        self.u.mem_write(INPUT_FP, SYNTHETIC_FP)
        self.u.mem_write(PAYLOAD, SYNTHETIC_PAYLOAD)
        self.calls = []
        self.executed = []
        self.comparisons = 0
        self.dispatches = []
        self.allocated = False
        self.freed = False
        self.u.hook_add(uc.UC_HOOK_CODE, self.code)

    def read(self, address, count):
        return bytes(self.u.mem_read(address, count))

    def word(self, address):
        return struct.unpack("<I", self.read(address, 4))[0]

    def lv(self, address):
        length = struct.unpack("<H", self.read(address, 2))[0]
        require(length <= 4096, "unbounded synthetic LV")
        return self.read(address + 2, length)

    def code(self, u, address, size, opaque):
        if address in HOOKS:
            r = [u.reg_read(reg) for reg in self.argument_regs]
            self.calls.append(dict(name=HOOKS[address], address=hex(address)))
            result = 0
            if address == GET_APPINFO:
                require(r[0] == PACKAGE, "get_appinfo must query the actual package argument")
                if self.installed:
                    # Both tested routines read only output+0x10. This field
                    # comes directly from their instructions, not a fabricated
                    # PackageManager/C++ object or installed-vector layout.
                    u.mem_write(r[1] + 0x10, struct.pack("<I", LOCAL_FP))
                else:
                    result = -1
            elif address == LOG:
                pass  # Message formatting/output is outside the tested branch.
            elif address == MEMSET:
                require(r[2] == 0x150 and STACK - 0x400 <= r[0] < STACK,
                    "unexpected memset ABI or destination")
                u.mem_write(r[0], bytes([r[1] & 255]) * r[2])
            elif address == MEMCPY:
                require(0 < r[2] <= 4096, "unexpected memcpy length")
                require(r[1] in (LOCAL_FP, PAYLOAD), "unexpected memcpy source")
                u.mem_write(r[0], self.read(r[1], r[2]))
            elif address == MALLOC:
                require(r[0] == len(SYNTHETIC_PAYLOAD) + 2 and not self.allocated,
                    "unexpected allocation ABI")
                self.allocated = True
                result = HEAP
            elif address == FREE:
                require(self.allocated and r[0] == HEAP and not self.freed,
                    "unexpected release ABI")
                self.freed = True
            elif address == RX_DISPATCH:
                require((r[0], r[1], r[2]) == (PACKAGE, PAYLOAD, len(SYNTHETIC_PAYLOAD)),
                    "receive dispatch must preserve package/payload/length")
                require(self.read(r[1], r[2]) == SYNTHETIC_PAYLOAD, "receive payload changed")
                self.dispatches.append(dict(direction="phone_to_watch", reached_edge=True,
                    payload_bytes=r[2], fingerprint_comparisons=self.comparisons))
            elif address == TX_DISPATCH:
                packet = r[0]
                require(r[1] == 0 and r[2] == 0, "unexpected packet send flags")
                require(self.word(packet) == 0x00160914, "actual packet header differs")
                require(struct.unpack("<H", self.read(packet + 8, 2))[0] == 9, "actual quickapp opcode differs")
                require(self.word(packet + 0x10) == PACKAGE, "actual packet package differs")
                require(self.lv(self.word(packet + 0x14)) == SYNTHETIC_FP,
                    "actual sender must attach all 20 local fingerprint bytes")
                require(self.lv(self.word(packet + 0x18)) == SYNTHETIC_PAYLOAD,
                    "actual sender must attach exact payload")
                self.dispatches.append(dict(direction="watch_to_phone", reached_edge=True,
                    payload_bytes=len(SYNTHETIC_PAYLOAD), attached_fingerprint_bytes=20))
            u.reg_write(self.regs.UC_ARM_REG_R0, result & 0xffffffff)
            u.reg_write(self.regs.UC_ARM_REG_PC, u.reg_read(self.regs.UC_ARM_REG_LR))
            return
        require(any(start <= address < end for start, end in CODE_RANGES),
            "unexpected firmware execution outside bounded functions: " + hex(address))
        self.executed.append(address)
        if address == 0x0c82e5c0:
            self.comparisons += 1

    @property
    def argument_regs(self):
        return [self.regs.UC_ARM_REG_R0, self.regs.UC_ARM_REG_R1,
            self.regs.UC_ARM_REG_R2, self.regs.UC_ARM_REG_R3]

    def call(self, address, *args):
        self.u.reg_write(self.regs.UC_ARM_REG_SP, STACK)
        self.u.reg_write(self.regs.UC_ARM_REG_LR, STOP | 1)
        for reg, value in zip(self.argument_regs, args):
            self.u.reg_write(reg, value)
        self.u.emu_start(address | 1, STOP, count=10000)
        require(self.u.reg_read(self.regs.UC_ARM_REG_PC) == STOP, "bounded firmware function did not return")
        require(self.u.reg_read(self.regs.UC_ARM_REG_SP) == STACK, "firmware stack ABI did not restore")
        require(len([c for c in self.calls if c["address"] == hex(GET_APPINFO)]) == 1,
            "each real routine must check AppInfo once")

    def result(self, name):
        return dict(scenario=name, passed=True, installed_outcome_injected=self.installed,
            firmware_instructions_executed=len(self.executed), fingerprint_comparisons=self.comparisons,
            dependency_hooks=self.calls, dispatch_edges=self.dispatches)


def run(raw):
    uc, regs = load_runtime()
    reports = []
    for nullable in (False, True):
        host = Replay(raw, uc, regs, False)
        host.call(VERIFY, PACKAGE, 0 if nullable else INPUT_FP, PAYLOAD, len(SYNTHETIC_PAYLOAD))
        require(not host.dispatches and host.comparisons == 0, "missing AppInfo must reject before fingerprint/dispatch")
        require(0x0c82e5a0 in host.executed and 0x0c82e5ea in host.executed,
            "real get_appinfo rejection branch must execute")
        reports.append(host.result("receive_missing_appinfo_" + ("null_fingerprint" if nullable else "fingerprint_present")))
    for mismatch in range(20):
        host = Replay(raw, uc, regs, True)
        changed = bytearray(SYNTHETIC_FP)
        changed[mismatch] ^= 1
        host.u.mem_write(INPUT_FP, bytes(changed))
        host.call(VERIFY, PACKAGE, INPUT_FP, PAYLOAD, len(SYNTHETIC_PAYLOAD))
        require(not host.dispatches and host.comparisons == mismatch + 1,
            "actual byte comparison must reject mismatched fingerprint byte " + str(mismatch))
        require(0x0c82e5c4 in host.executed, "real mismatch rejection branch must execute")
        reports.append(host.result("receive_fingerprint_mismatch_byte_" + str(mismatch)))
    host = Replay(raw, uc, regs, True)
    host.call(VERIFY, PACKAGE, INPUT_FP, PAYLOAD, len(SYNTHETIC_PAYLOAD))
    require(host.comparisons == 20 and len(host.dispatches) == 1, "matching 20-byte fingerprint must reach only dispatch edge")
    require(0x0c82e606 in host.executed, "actual receive dispatch call must execute")
    reports.append(host.result("receive_fingerprint_match_reaches_dispatch_edge"))
    for installed in (False, True):
        host = Replay(raw, uc, regs, installed)
        host.call(SEND, PACKAGE, PAYLOAD, len(SYNTHETIC_PAYLOAD))
        if installed:
            require(len(host.dispatches) == 1 and host.allocated and host.freed,
                "identity-present actual sender must build and release packet at dispatch edge")
            require(0x0c830af2 in host.executed, "actual send dispatch call must execute")
        else:
            require(not host.dispatches and not host.allocated, "missing AppInfo must block send before allocation/dispatch")
            require(0x0c830b06 in host.executed, "actual send missing-AppInfo branch must execute")
        reports.append(host.result("send_identity_present_dispatch_edge" if installed else "send_missing_appinfo"))
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-private-ap", action="store_true", help="explicit opt-in to execute pinned local AP bytes in Unicorn")
    parser.add_argument("--firmware-ap", type=Path, help="authorized pinned AP; otherwise use existing private build configuration")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.execute_private_ap:
        print(json.dumps(dict(status="skipped", reason="requires explicit --execute-private-ap",
            private_ap_read=False, firmware_executed=False, device_accessed=False)))
        return
    if args.firmware_ap:
        path = args.firmware_ap
    else:
        sys.path.insert(0, str(ROOT))
        from build_settings import firmware_path
        path = firmware_path("ap")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == AP_SHA256, "AP differs from pinned P65 3.100.043")
    guards = []
    for name, address, size, digest in WINDOWS:
        offset = address - AP_BASE
        require(hashlib.sha256(raw[offset:offset + size]).hexdigest() == digest, "bounded routine guard mismatch: " + name)
        guards.append(dict(function=name, entry=hex(address), guarded_bytes=size, sha256=digest))
    cases = run(raw)
    report = dict(passed=True, cases=len(cases), scenarios=cases, ap_sha256=AP_SHA256, guarded_functions=guards,
        executed_firmware_functions=["verify_phone_message", "send_wearmsg"], ap_mapping="read/execute only",
        routing_subset_executed=True, appinfo_lookup_stubbed=True, registration_verified=False,
        executed_code_ranges=[dict(start=hex(start), end_exclusive=hex(end)) for start, end in CODE_RANGES],
        tested_abi=dict(verify_phone_message="r0=package, r1=fingerprint, r2=payload, r3=length",
            send_wearmsg="r0=package, r1=payload, r2=length",
            get_appinfo="r0=package, r1=output; return 0/-1; output+0x10=local fingerprint pointer"),
        real_fingerprint_comparison_executed=True, tested_comparison_stubbed=False,
        get_appinfo_boundary="injected -1 failure or 0 success with out+0x10 pointing to a synthetic 20-byte fingerprint",
        dependency_hooks=[dict(name=name, address=hex(address)) for address, name in HOOKS.items()],
        package_manager_executed=False, identity_registration_proven=False, signature_cryptography_executed=False,
        dispatch_implementation_executed=False, physical_mifitness_delivery_proven=False,
        single_bin_mifitness_export_proven=False, fingerprint_source="synthetic bytes 0x30..0x43",
        device_accessed=False, private_signer_read=False, personal_audio_read=False, firmware_modified=False,
        scope="actual fixed AP rejection/20-byte comparison/packet construction branches; injected AppInfo and terminal dispatch boundaries")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
