"""Deterministic SYNTHETIC test data. No game execution or reproduction is asserted."""

from __future__ import annotations

import copy
import json
import struct
import zlib
from decimal import Decimal
from pathlib import Path

from .validator import HERE, sha256


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def demo_png():
    """A small lossless test card visibly reading DEMO, not a game screenshot."""
    glyphs = [
        ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
        ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
        ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
        ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    ]
    scale, width, height = 6, 160, 64
    rows = []
    for y in range(height):
        row = bytearray(b"\x00")
        for x in range(width):
            gx, gy = (x - 11) // scale, (y - 11) // scale
            lit = (0 <= gx < 24 and 0 <= gy < 7 and gx // 6 < 4
                   and gx % 6 < 5 and glyphs[gx // 6][gy][gx % 6] == "1")
            row.extend((255, 255, 255) if lit else (125, 15, 25))
        rows.append(row)
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"tEXt", b"Description\x00SYNTHETIC DEMO ONLY - NOT GAME EXECUTION EVIDENCE")
            + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


def identity(name):
    return {"name": name, "kind": "unspecified", "contribution": "Synthetic fixture identity; no actual participation", "links": []}


def uid(number):
    return "00000000-0000-4000-8000-" + str(number).zfill(12)


def input_state(held=None, controls=()):
    return {"held_ball": held, "active_controls": list(controls)}


def point(x, y):
    return {"x": str(x), "y": str(y)}


def make_execution(*, reverse=False, partial=False):
    """Generate abstract internally consistent declarations, not a feasible tower."""
    start = {"start_class": "corporation-equivalent-v1",
             "initialization": "[DEMO] Synthetic three-ball starter plus inventory; never loaded into a game",
             "randomness": "[DEMO] Deterministic test data, not a game RNG observation",
             "identity_policy": "Persistent local IDs b000..b299; no native pointer identity is assumed",
             "balls": [], "connections": []}
    for index in range(300):
        start["balls"].append({"id": f"b{index:03d}", "type": "common",
                               "role": "construction" if index < 3 else "inventory",
                               "position": point(index * 10, 100) if index < 3 else None,
                               "properties": {}})
    for index, (a, b) in enumerate(((0, 1), (1, 2), (2, 0))):
        start["connections"].append({"id": f"starter{index}", "a": f"b{a:03d}",
                                     "b": f"b{b:03d}", "type": "strand", "properties": {}})
    final = {"balls": [{k: copy.deepcopy(v) for k, v in ball.items() if k != "type"} for ball in start["balls"]],
             "connections": copy.deepcopy(start["connections"]), "description": "[DEMO] Abstract test structure; physical feasibility is not asserted"}
    events, quiet = [], []
    def at(game, wall=None):
        value = Decimal(str(game))
        return {"game_s": str(value), "wall_s": str(value * (3 if reverse else 2) if wall is None else Decimal(str(wall)))}
    def marker(name, phase, time, height=None):
        return {"id": name, "at": time, "kind": "marker", "phase": phase,
                "input_state": input_state(), "height_m": height,
                "height_resolution_m": "0.1" if height else None, "notes": "[DEMO] Synthetic phase boundary"}
    events.append(marker("start", "construction_started", at(0)))
    order = list(range(3, 300))
    if reverse:
        order.reverse()
    if partial:
        order = order[:2]
    previous = None
    for step, ball_index in enumerate(order):
        ball = f"b{ball_index:03d}"
        base = Decimal(step * (2 if reverse else 1))
        begin, picked, release, observed = (f"{ball}:{suffix}" for suffix in ("begin", "picked", "release", "observed"))
        if previous:
            quiet.append({"from": previous, "to": begin, **input_state(), "gameplay": "normal"})
        def interaction(name, time, operation, parameters, state):
            return {"id": name, "at": at(time), "kind": "interaction", "operation": operation,
                    "objects": {"balls": [ball], "connections": []}, "parameters": parameters,
                    "input_state": state, "notes": "[DEMO] Synthetic operation, not an executed input"}
        events.append(interaction(begin, base, "pickup_begin", {}, input_state(None, ["pointer_primary"])))
        events.append(interaction(picked, base + Decimal("0.01"), "pickup_end", {"begin": begin, "result": "held"}, input_state(ball, ["pointer_primary"])))
        position = point(ball_index, 100 + ball_index)
        events.append(interaction(release, base + Decimal("0.02"), "release", {"position": position, "purpose": "attach", "tolerance": None}, input_state()))
        new_connections = [{"id": f"edge{ball_index}_{anchor}", "a": ball, "b": f"b{anchor:03d}", "type": "strand", "properties": {}} for anchor in (0, 1)]
        events.append({"id": observed, "at": at(base + Decimal("0.03")), "kind": "state", "cause": release,
                       "changes": {"ball_roles": [{"ball": ball, "from": "inventory", "to": "construction", "reason": "[DEMO] Synthetic attachment outcome"}],
                                   "ball_properties": [], "connections_added": new_connections, "connections_removed": [], "connection_properties": []},
                       "positions": [{"ball": ball, "position": position}], "input_state": input_state(), "notes": "[DEMO] Declared test state; not a physics prediction"})
        final["balls"][ball_index]["role"] = "construction"
        final["balls"][ball_index]["position"] = position
        final["connections"].extend(new_connections)
        previous = observed
    construction = hold = None
    if not partial:
        construction = at(base + Decimal("0.04"))
        hold = {"wall_s": "47" if reverse else "45", "game_s": "31" if reverse else "30"}
        end = {clock: str(Decimal(construction[clock]) + Decimal(hold[clock])) for clock in construction}
        events.append(marker("hands_off", "hands_off_started", construction))
        events.append(marker("measurement", "measured", end, "12.4" if reverse else "12.3"))
        quiet.append({"from": previous, "to": "hands_off", **input_state(), "gameplay": "normal"})
        quiet.append({"from": "hands_off", "to": "measurement", **input_state(), "gameplay": "normal"})
    clock = {"basis": "measured", "resolution_s": "0.001", "method": "[DEMO] Synthetic values exercise measured-clock serialization; they are not measurements"}
    execution = {"completeness": "partial" if partial else "complete",
                 "process_claim": {"mode": "human_only" if partial else "human_and_machine" if reverse else "machine_only",
                     "description": "[DEMO] Synthetic attribution example only; no actual discovery, construction or oversight occurred"},
                 "environment": {"game": "World of Goo", "version": "[DEMO] no native game",
                                 "platform": "synthetic fixture generator", "executable_sha256": "0" * 64,
                                 "physics_assets": [{"name": "[DEMO] placeholder", "sha256": "0" * 64}],
                                 "settings": {}, "gameplay_modifications": [], "state_injection_during_construction": False},
                 "coordinates": {"description": "[DEMO] Arbitrary test XY coordinates; not calibrated to any game"},
                 "start_file": "start.json", "final_file": "final.json", "event_files": ["events/0001.jsonl"],
                 "timing": {"wall": copy.deepcopy(clock), "game": copy.deepcopy(clock),
                            "synchronization_uncertainty_s": None, "synchronization_notes": "[DEMO] No real acquisition occurred",
                            "construction": construction, "hold": hold, "total": copy.deepcopy(events[-1]["at"])},
                 "quiet_periods": quiet, "image": None if partial else {"path": "finished.png", "origin": "demo_image", "caption": "[DEMO] Synthetic test card, not a finished game tower"},
                 "native_save": None if partial else {"path": "save/pers3.dat", "origin": "demo_save",
                     "profile": "[DEMO] No native profile exists",
                     "restore_instructions": "[DEMO] Do not load this placeholder into a game; it is not restorable",
                     "notes": "[DEMO] Synthetic opaque bytes exercise required-save packaging only; no actual save or tower exists"},
                 "custom_operations": [], "custom_controls": []}
    payloads = {"start.json": json_bytes(start), "final.json": json_bytes(final),
                "events/0001.jsonl": b"".join((json.dumps(e, separators=(",", ":")) + "\n").encode() for e in events)}
    if not partial:
        payloads["finished.png"] = demo_png()
        payloads["save/pers3.dat"] = b"[DEMO] SYNTHETIC SAVE PLACEHOLDER - NOT A NATIVE GAME SAVE\n\x00\xff"
    return execution, payloads


def write_bundle(root, manifest_name, manifest, payloads):
    """Generator output only: requires a new directory and never overwrites a bundle."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    record = copy.deepcopy(manifest)
    record["files"] = [{"path": name, "format": {".json": "json", ".jsonl": "jsonl", ".png": "png", ".jpg": "jpeg", ".dat": "native_save"}[Path(name).suffix], "sha256": sha256(raw)} for name, raw in sorted(payloads.items())]
    for name, raw in payloads.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    raw = json_bytes(record)
    (root / manifest_name).write_bytes(raw)
    return {"id": record["id"], "sha256": sha256(raw)}


def build_trial(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    profile_path = HERE / "rulesets" / "corporation-state-300-v1.json"
    profile = json.loads(profile_path.read_text())
    common = {"version": "0.2", "purpose": "demo", "revises": None,
              "ruleset": {"id": profile["id"], "sha256": sha256(profile_path.read_bytes())}, "files": [], "extensions": {}}
    execution, payloads = make_execution()
    submission = {"format": "goo-ai-arena.submission", **copy.deepcopy(common), "id": uid(1),
                  "claim_kind": "synthetic_fixture", "title": "[DEMO] Synthetic submission contract example",
                  "creators": [identity("Demo creator")], "claim": {"height_m": "12.3", "description": "[DEMO] Placeholder height; no actual result", "measurement_method": "[DEMO] Test native-measurement fields only"},
                  "execution": execution, "about": {"background": "[DEMO] Optional public background", "method": "[DEMO] Test generator", "tools": [{"name": "arena_contract.fixtures", "version": "0.2", "role": "Generates synthetic fixtures", "url": None}], "hardware": None, "preparation": None, "credits": [], "links": []},
                  "reproduction_guide": {"overview": "[DEMO] Advice is nonbinding and is not an executed history", "notes": [{"event_ids": ["b003:release"], "instruction": "Observe the attachment and adjust your own timing if needed.", "rationale": "Reproduction timing need not match the original.", "basis": "advice"}]}, "external_evidence": []}
    original = write_bundle(destination / "submission", "submission.json", submission, payloads)
    report = {"format": "goo-ai-arena.reproduction-report", **copy.deepcopy(common), "id": uid(2),
              "target": original, "title": "[DEMO] Synthetic successful reproduction report", "reporter": identity("Demo reproducer"),
              "relation_to_creator": "Synthetic identities from the same fixture generator; no independence claimed",
              "verdict": "reproduced", "method": "[DEMO] Reverse placement order and different timings; no actual execution",
              "differences": "[DEMO] Same declared final connections using a different order and clocks; claimed height differs",
              "shared_dependencies": "All examples share the same test generator", "evidence_limitations": "Entirely synthetic; no physical feasibility or reproduction is asserted", "execution": None, "external_evidence": []}
    report["execution"], reproduction_payloads = make_execution(reverse=True)
    reproduced = write_bundle(destination / "reproduced", "report.json", report, reproduction_payloads)
    failed = copy.deepcopy(report)
    failed.update(id=uid(3), title="[DEMO] Synthetic stopped attempt", verdict="not_reproduced",
                  method="[DEMO] Partial trace ends at the last recorded synthetic event")
    failed["execution"], failed_payloads = make_execution(partial=True)
    write_bundle(destination / "failed", "report.json", failed, failed_payloads)
    inconclusive = copy.deepcopy(report)
    inconclusive.update(id=uid(4), title="[DEMO] Synthetic inconclusive report", verdict="inconclusive", execution=None,
                        method="[DEMO] No usable trace was retained; the example explains missing evidence without inventing events")
    write_bundle(destination / "inconclusive", "report.json", inconclusive, {})
    revised = copy.deepcopy(submission)
    revised.update(id=uid(5), revises=original, title="[DEMO] Separate revision with improved guidance")
    revised["reproduction_guide"]["overview"] = "[DEMO] Improved advice in a new immutable version; the old record is unchanged"
    write_bundle(destination / "revision", "submission.json", revised, payloads)
    withdrawal = {"format": "goo-ai-arena.withdrawal", "version": "0.2", "id": uid(6), "purpose": "demo", "target": reproduced,
                  "author": identity("Demo reproducer"), "reason": "[DEMO] Illustrates withdrawing an earlier report without deleting it", "files": []}
    write_bundle(destination / "withdrawal", "withdrawal.json", withdrawal, {})
    index = {"purpose": "demo", "notice": "SYNTHETIC FIXTURES ONLY. No native builds or reproduction claims. Never publish as competition records.",
             "bundles": {"submission": "submission", "reproduced": "reproduced", "failed": "failed", "inconclusive": "inconclusive", "revision": "revision", "withdrawal": "withdrawal"}}
    (destination / "trial-index.json").write_bytes(json_bytes(index))
    return index
