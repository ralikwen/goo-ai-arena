import copy
import base64
import errno
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from decimal import Decimal, localcontext
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from arena_contract.fixtures import build_trial, input_state, json_bytes, uid
from arena_contract.validator import BrowserDecoder, HERE, SCHEMA, read_safe, sha256, validate_bundle

ROOT = HERE.parent


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "var").mkdir(exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix="arena-contract-tests-", dir=ROOT / "var")
        cls.work = Path(cls.temporary.name)
        cls.fixtures = cls.work / "fixtures"
        build_trial(cls.fixtures)
        cls.decoder = BrowserDecoder()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.case_temp = tempfile.TemporaryDirectory(prefix="case-", dir=self.work)
        self.case = Path(self.case_temp.name) / "bundle"
        self.use("submission")

    def tearDown(self):
        self.case_temp.cleanup()

    def use(self, name):
        # Each selection gets a new directory; no user-owned bundle is overwritten.
        self.case = Path(self.case_temp.name) / name
        shutil.copytree(self.fixtures / name, self.case)
        self.manifest = self.case / ("submission.json" if name in {"submission", "revision"}
                                     else "withdrawal.json" if name == "withdrawal" else "report.json")

    def manifest_data(self):
        return json.loads(self.manifest.read_text())

    def edit_manifest(self, edit):
        value = self.manifest_data()
        edit(value)
        self.manifest.write_bytes(json_bytes(value))

    def edit_artifact(self, path, edit, *, jsonl=False):
        file = self.case / path
        value = [json.loads(line) for line in file.read_text().splitlines()] if jsonl else json.loads(file.read_text())
        edit(value)
        raw = b"".join((json.dumps(v) + "\n").encode() for v in value) if jsonl else json_bytes(value)
        file.write_bytes(raw)
        self.rehash(path)

    def edit_events(self, edit):
        self.edit_artifact("events/0001.jsonl", edit, jsonl=True)

    def rehash(self, path):
        def edit(record):
            for item in record["files"]:
                if item["path"] == path:
                    item["sha256"] = sha256((self.case / path).read_bytes())
        self.edit_manifest(edit)

    def result(self, **kwargs):
        options = {"allow_demo": True, "references": [self.fixtures / "submission"], "decoder": self.decoder}
        if self.case.name == "withdrawal":
            options["references"].append(self.fixtures / "reproduced")
        # A mutated test case is a new draft, not a revision reusing a published ID.
        if self.manifest.name == "submission.json" and self.case.name != "revision":
            options["references"] = []
        options.update(kwargs)
        result = validate_bundle(self.case, **options)
        validator = Draft202012Validator({"$defs": SCHEMA["$defs"], "$ref": "#/$defs/Admission"})
        self.assertTrue(validator.is_valid(result), list(validator.iter_errors(result)))
        return result

    def expect(self, status, code=None, **kwargs):
        result = self.result(**kwargs)
        self.assertEqual(result["status"], status, result)
        if code:
            self.assertIn(code, {i["code"] for i in result["errors"] + result["warnings"]}, result)
        return result

    def test_schema_is_valid_draft_2020_12(self):
        Draft202012Validator.check_schema(SCHEMA)

    def test_complete_fixture_and_actual_png_decoder(self):
        self.expect("admitted", "SYNTHETIC_FIXTURE")

    def test_normal_mode_rejects_demo(self):
        self.expect("needs_correction", "DEMO_NOT_ALLOWED", allow_demo=False)

    def test_unexecuted_proposal_is_rejected(self):
        self.edit_manifest(lambda r: r.update(claim_kind="proposal"))
        self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_omitted_optional_guidance_background_and_coordinates(self):
        def edit(record):
            record.pop("about")
            record.pop("reproduction_guide")
            record["execution"].pop("coordinates")
        self.edit_manifest(edit)
        self.expect("admitted")

    def test_uninterpretable_coordinate_notes_are_not_an_admission_gate(self):
        self.edit_manifest(lambda r: r["execution"].update(coordinates={"description": "Another convention, currently unexplained"}))
        self.expect("admitted")

    def test_discovery_building_claim_is_required(self):
        self.edit_manifest(lambda r: r["execution"].pop("process_claim"))
        self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_process_claim_cannot_be_null_or_have_unknown_mode(self):
        for value in (None, {"mode": "verified_ai", "description": "Not an allowed category"}):
            with self.subTest(value=value):
                self.edit_manifest(lambda r: r["execution"].update(process_claim=value))
                self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_process_claim_needs_nonblank_role_explanation(self):
        for description in (None, "", " \n\t"):
            with self.subTest(description=description):
                self.edit_manifest(lambda r: r["execution"]["process_claim"].update(description=description))
                self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_all_process_modes_are_eligible_self_declared_claims(self):
        for mode in ("machine_only", "human_and_machine", "human_only"):
            with self.subTest(mode=mode):
                self.edit_manifest(lambda r: r["execution"]["process_claim"].update(mode=mode))
                self.expect("admitted", "PROCESS_CLAIM_UNVERIFIED")

    def test_reproduction_declares_its_own_process_not_targets(self):
        self.use("reproduced")
        self.assertEqual(self.manifest_data()["execution"]["process_claim"]["mode"], "human_and_machine")
        target = json.loads((self.fixtures / "submission" / "submission.json").read_text())
        self.assertEqual(target["execution"]["process_claim"]["mode"], "machine_only")
        self.expect("admitted", "PROCESS_CLAIM_UNVERIFIED")
        self.edit_manifest(lambda r: r["execution"].pop("process_claim"))
        self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_partial_attempt_still_declares_its_process(self):
        self.use("failed")
        self.edit_manifest(lambda r: r["execution"].pop("process_claim"))
        self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_missing_and_null_clocks_are_rejected(self):
        for value in (None, "missing"):
            with self.subTest(value=value):
                def edit(events):
                    if value == "missing":
                        events[1]["at"].pop("game_s", None)
                    else:
                        events[1]["at"]["game_s"] = value
                self.edit_events(edit)
                self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_null_start_and_final_are_not_missing_optional_evidence(self):
        for path in ("start.json", "final.json"):
            with self.subTest(path=path):
                original = (self.case / path).read_bytes()
                (self.case / path).write_bytes(b"null\n")
                self.rehash(path)
                self.expect("needs_correction", "SCHEMA_MISMATCH")
                (self.case / path).write_bytes(original)
                self.rehash(path)

    def test_malformed_event_id_still_has_a_valid_error_response(self):
        self.edit_events(lambda events: events[1].update(id={"invalid": "id"}))
        self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_estimated_clock_basis_is_rejected(self):
        self.edit_manifest(lambda r: r["execution"]["timing"]["wall"].update(basis="estimated"))
        self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_clocks_are_monotonic(self):
        self.edit_events(lambda events: events[3]["at"].update(game_s="0"))
        self.expect("needs_correction", "TIMELINE_INCONSISTENT")

    def test_duration_must_match_actual_boundaries(self):
        self.edit_manifest(lambda r: r["execution"]["timing"]["construction"].update(wall_s="0"))
        self.expect("needs_correction", "TIMELINE_INCONSISTENT")

    def test_missing_event_reference_has_location(self):
        self.edit_events(lambda events: events[4].update(cause="absent"))
        result = self.expect("needs_correction", "UNDEFINED_REFERENCE")
        issue = next(i for i in result["errors"] if i["code"] == "UNDEFINED_REFERENCE")
        self.assertEqual((issue["file"], issue["line"], issue["event_id"]), ("events/0001.jsonl", 5, "b003:observed"))

    def test_duplicate_event_ids(self):
        self.edit_events(lambda events: events[2].update(id=events[1]["id"]))
        self.expect("needs_correction", "DUPLICATE_ID")

    def test_hash_mismatch(self):
        (self.case / "finished.png").write_bytes(b"different bytes")
        self.expect("needs_correction", "HASH_MISMATCH")

    def test_missing_image_file(self):
        (self.case / "finished.png").unlink()
        self.expect("needs_correction", "MISSING_FILE")

    def test_unreadable_image_is_not_admitted(self):
        (self.case / "finished.png").write_bytes(b"not PNG")
        self.rehash("finished.png")
        self.expect("needs_correction", "IMAGE_INVALID")

    def test_all_declared_images_are_decoded(self):
        path = self.case / "extra.png"
        path.write_bytes(b"not a PNG")
        self.edit_manifest(lambda r: r["files"].append({"path": "extra.png", "format": "png", "sha256": sha256(path.read_bytes())}))
        self.expect("needs_correction", "IMAGE_INVALID")

    def test_decoder_timeout_is_pending_and_cleans_up_its_process_group(self):
        decoder = BrowserDecoder(timeout_s=0.001)
        result = decoder((self.case / "finished.png").read_bytes(), "png")
        self.assertEqual(result[0], "unavailable")

    def test_decoder_failure_is_pending_not_game_illegality(self):
        self.expect("pending", "INFRASTRUCTURE_UNAVAILABLE", decoder=lambda raw, fmt: ("unavailable", "Resource unavailable"))

    def test_screenshot_is_required_for_completed_submission(self):
        self.edit_manifest(lambda r: r["execution"].update(image=None))
        self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_save_descriptor_cannot_be_omitted(self):
        self.edit_manifest(lambda r: r["execution"].pop("native_save"))
        self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_save_is_required_for_completed_submission(self):
        self.edit_manifest(lambda r: r["execution"].update(native_save=None))
        self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_save_is_required_for_successful_reproduction(self):
        self.use("reproduced")
        self.edit_manifest(lambda r: r["execution"].update(native_save=None))
        self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_missing_save_file(self):
        (self.case / "save/pers3.dat").unlink()
        self.expect("needs_correction", "MISSING_FILE")

    def test_save_must_be_declared_in_bundle_not_just_linked(self):
        def edit(record):
            record["files"] = [item for item in record["files"] if item["format"] != "native_save"]
            record["external_evidence"] = [{"url": "https://example.invalid/pers3.dat",
                "sha256": "0" * 64, "media_type": "application/octet-stream", "description": "External save cannot replace the required attachment"}]
        self.edit_manifest(edit)
        (self.case / "save/pers3.dat").unlink()
        self.expect("needs_correction", "MISSING_FILE")

    def test_save_hash_must_match(self):
        (self.case / "save/pers3.dat").write_bytes(b"[DEMO] different placeholder bytes")
        self.expect("needs_correction", "HASH_MISMATCH")

    def test_save_must_not_be_empty(self):
        (self.case / "save/pers3.dat").write_bytes(b"")
        self.rehash("save/pers3.dat")
        self.expect("needs_correction", "SAVE_EMPTY")

    def test_save_reference_cannot_point_to_graph_json(self):
        self.edit_manifest(lambda r: r["execution"]["native_save"].update(path="final.json"))
        self.expect("needs_correction", "FILE_FORMAT")

    def test_save_descriptor_requires_restoration_metadata(self):
        original = self.manifest.read_bytes()
        for field in ("path", "origin", "profile", "restore_instructions", "notes"):
            with self.subTest(field=field):
                self.manifest.write_bytes(original)
                self.edit_manifest(lambda r: r["execution"]["native_save"].pop(field))
                self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_save_origins_are_separated_by_purpose_in_schema(self):
        for purpose, wrong_origin in (("demo", "game_save"), ("competition", "demo_save")):
            with self.subTest(purpose=purpose):
                record = self.manifest_data()
                record["purpose"] = purpose
                record["claim_kind"] = "synthetic_fixture" if purpose == "demo" else "reported_execution"
                record["execution"]["image"]["origin"] = "demo_image" if purpose == "demo" else "game_screenshot"
                record["execution"]["native_save"]["origin"] = wrong_origin
                validator = Draft202012Validator({"$defs": SCHEMA["$defs"], "$ref": "#/$defs/Submission"})
                self.assertFalse(validator.is_valid(record))

    def test_demo_save_notes_must_expose_synthetic_origin(self):
        self.edit_manifest(lambda r: r["execution"]["native_save"].update(notes="Missing explicit demo label"))
        self.expect("needs_correction", "DEMO_LABEL")

    def test_save_bytes_are_opaque_unchanged_and_not_certified_restorable(self):
        path = self.case / "save/pers3.dat"
        before = path.read_bytes()
        self.assertIn(b"\xff", before)  # Intentionally not UTF-8; never a native save.
        self.expect("admitted", "NATIVE_SAVE_UNVERIFIED")
        self.assertEqual(before, path.read_bytes())

    def test_unreadable_save_is_pending(self):
        def unavailable(root, relative):
            if relative == "save/pers3.dat":
                raise PermissionError(errno.EACCES, "Test permission failure")
            return read_safe(root, relative)
        with patch("arena_contract.validator.read_safe", side_effect=unavailable):
            self.expect("pending", "INFRASTRUCTURE_UNAVAILABLE")

    def test_save_symlink_is_rejected(self):
        path = self.case / "save/pers3.dat"
        path.unlink()
        path.symlink_to(self.fixtures / "submission" / "save/pers3.dat")
        self.expect("needs_correction", "UNSAFE_PATH")

    def test_historical_contract_is_pending_not_silently_reinterpreted(self):
        self.edit_manifest(lambda r: (r.update(version="0.1"), r["execution"].pop("native_save")))
        self.expect("pending", "UNSUPPORTED_VERSION")

    def test_complete_failed_attempt_can_lack_a_save(self):
        self.use("reproduced")
        self.edit_manifest(lambda r: (r.update(verdict="not_reproduced"), r["execution"].update(native_save=None)))
        self.expect("admitted")

    def test_undeclared_file(self):
        (self.case / "extra.txt").write_text("not declared")
        self.expect("needs_correction", "UNDECLARED_FILE")

    def test_symlink_is_rejected(self):
        (self.case / "link.txt").symlink_to(self.fixtures / "submission" / "start.json")
        self.expect("needs_correction", "UNSAFE_PATH")

    def test_permission_failure_is_pending_not_missing_evidence(self):
        def unavailable(root, relative):
            if relative == "events/0001.jsonl":
                raise PermissionError(errno.EACCES, "Test permission failure")
            return read_safe(root, relative)
        with patch("arena_contract.validator.read_safe", side_effect=unavailable):
            self.expect("pending", "INFRASTRUCTURE_UNAVAILABLE")

    def test_unreferenced_jsonl_artifacts_must_still_be_well_formed(self):
        path = self.case / "notes.jsonl"
        path.write_bytes(b"not json\n")
        self.edit_manifest(lambda r: r["files"].append({"path": "notes.jsonl", "format": "jsonl", "sha256": sha256(path.read_bytes())}))
        self.expect("needs_correction", "JSON_INVALID")

    def test_jsonl_null_is_not_an_object(self):
        path = self.case / "notes.jsonl"
        path.write_bytes(b"null\n")
        self.edit_manifest(lambda r: r["files"].append({"path": "notes.jsonl", "format": "jsonl", "sha256": sha256(path.read_bytes())}))
        self.expect("needs_correction", "JSONL_LAYOUT")

    def test_traversal_is_rejected_with_valid_admission_response(self):
        self.edit_manifest(lambda r: r["files"][0].update(path="x/../outside.json"))
        self.expect("needs_correction", "UNSAFE_PATH")

    def test_duplicate_json_keys(self):
        raw = self.manifest.read_bytes().replace(b'"version": "0.2",', b'"version": "0.2", "version": "0.2",', 1)
        self.manifest.write_bytes(raw)
        self.expect("needs_correction", "DUPLICATE_KEY")

    def test_fractional_json_numbers_are_rejected(self):
        self.edit_manifest(lambda r: r["claim"].update(height_m=12.3))
        self.expect("needs_correction", "JSON_INVALID")

    def test_jsonl_requires_final_lf(self):
        file = self.case / "events/0001.jsonl"
        file.write_bytes(file.read_bytes().rstrip(b"\n"))
        self.rehash("events/0001.jsonl")
        self.expect("needs_correction", "JSONL_LAYOUT")

    def test_unused_material_does_not_qualify(self):
        def events_edit(events):
            event = events[-3]
            event["changes"]["ball_roles"] = []
            event["changes"]["connections_added"] = []
        self.edit_events(events_edit)
        def final_edit(final):
            final["balls"][-1]["role"] = "inventory"
            final["connections"] = [c for c in final["connections"] if c["a"] != "b299"]
        self.edit_artifact("final.json", final_edit)
        self.expect("needs_correction", "RULE_VIOLATION")

    def test_reinforcement_consumption_counts_as_use(self):
        def events_edit(events):
            events[-4]["parameters"]["purpose"] = "reinforce"
            events[-4]["objects"]["connections"] = ["starter0"]
            event = events[-3]
            event["changes"]["ball_roles"][0].update(to="consumed", reason="Reported reinforcement consumption")
            event["changes"]["connections_added"] = []
            event["positions"] = []
        self.edit_events(events_edit)
        def final_edit(final):
            final["balls"][-1].update(role="consumed", position=None)
            final["connections"] = [c for c in final["connections"] if c["a"] != "b299"]
        self.edit_artifact("final.json", final_edit)
        self.expect("admitted")

    def test_material_birth_is_a_contradiction(self):
        self.edit_events(lambda events: events[4]["changes"]["ball_roles"][0].update(ball="new_ball"))
        self.expect("needs_correction", "UNDEFINED_REFERENCE")

    def test_extra_starting_material_is_rejected(self):
        self.edit_artifact("start.json", lambda start: start["balls"].append({**copy.deepcopy(start["balls"][-1]), "id": "extra"}))
        self.expect("needs_correction", "RULE_VIOLATION")

    def test_prebuilt_start_is_excluded(self):
        self.edit_artifact("start.json", lambda start: start["balls"][3].update(role="construction"))
        self.expect("needs_correction", "RULE_VIOLATION")

    def test_final_state_is_consistent_with_declared_transitions(self):
        self.edit_artifact("final.json", lambda final: final["connections"].pop())
        self.expect("needs_correction", "FINAL_STATE_MISMATCH")

    def test_connectivity_is_not_a_new_requirement(self):
        self.edit_events(lambda events: [event["changes"].update(connections_added=[]) for event in events if event["kind"] == "state"])
        self.edit_artifact("final.json", lambda final: final.update(connections=final["connections"][:3]))
        self.expect("admitted")

    def test_short_hold_does_not_qualify(self):
        self.edit_events(lambda events: events[-1]["at"].update(game_s=str(Decimal(events[-2]["at"]["game_s"]) + 29)))
        def edit(record):
            timing = record["execution"]["timing"]
            timing["hold"]["game_s"] = "29"
            timing["total"]["game_s"] = str(Decimal(timing["construction"]["game_s"]) + 29)
        self.edit_manifest(edit)
        self.expect("needs_correction", "RULE_VIOLATION")

    def test_hold_needs_explicit_no_input_evidence(self):
        self.edit_manifest(lambda r: r["execution"]["quiet_periods"].pop())
        self.expect("needs_correction", "RULE_VIOLATION")

    def test_quiet_interval_cannot_hide_actions(self):
        self.edit_manifest(lambda r: r["execution"]["quiet_periods"].append({"from": "start", "to": "measurement", **input_state(), "gameplay": "normal"}))
        self.expect("needs_correction", "QUIET_CONTRADICTION")

    def test_contradictory_overlapping_quiet_declarations(self):
        def edit(record):
            interval = copy.deepcopy(record["execution"]["quiet_periods"][-1])
            interval["gameplay"] = "paused"
            record["execution"]["quiet_periods"].append(interval)
        self.edit_manifest(edit)
        self.expect("needs_correction", "QUIET_CONTRADICTION")

    def test_active_control_during_final_hold(self):
        self.edit_events(lambda events: events[-2]["input_state"].update(active_controls=["whistle"]))
        self.expect("needs_correction", "RULE_VIOLATION")

    def test_custom_operation_is_admitted_without_a_physics_model(self):
        def manifest_edit(record):
            record["execution"]["custom_operations"].append({"id": "x:custom_release", "meaning": "A declared ordinary-input release technique", "at_means": "Input release boundary", "parameters": []})
        self.edit_manifest(manifest_edit)
        self.edit_events(lambda events: events[3].update(operation="x:custom_release", parameters={}))
        self.expect("admitted", "CUSTOM_OPERATION_NOT_MODELED")

    def test_undefined_custom_operation_needs_correction(self):
        self.edit_events(lambda events: events[3].update(operation="x:undefined", parameters={}))
        self.expect("needs_correction", "UNDEFINED_OPERATION")

    def test_custom_parameter_type_and_reference_checks(self):
        self.edit_manifest(lambda r: r["execution"]["custom_operations"].append({
            "id": "x:placement", "meaning": "A declared input method", "at_means": "Actual input release",
            "parameters": [{"name": "ball", "type": "ball_id", "required": True, "meaning": "Placed material ID"}]}))
        self.edit_events(lambda events: events[3].update(operation="x:placement", parameters={"ball": "absent"}))
        self.expect("needs_correction", "UNDEFINED_REFERENCE")

    def test_fast_inputs_are_not_rate_limited_or_rounded(self):
        with localcontext() as context:
            context.prec = 200
            def events_edit(events):
                for event in events[:-1]:
                    event["at"] = {k: format(Decimal(v) / Decimal("1e40"), "f") for k, v in event["at"].items()}
                events[-1]["at"] = {k: format(Decimal(events[-2]["at"][k]) + Decimal("30"), "f") for k in events[-2]["at"]}
            self.edit_events(events_edit)
            events = [json.loads(line) for line in (self.case / "events/0001.jsonl").read_text().splitlines()]
            self.edit_manifest(lambda r: r["execution"]["timing"].update(construction=events[-2]["at"], hold={"wall_s": "30", "game_s": "30"}, total=events[-1]["at"]))
            self.expect("admitted")

    def test_construction_pause_advances_wall_time_only(self):
        def events_edit(events):
            pause = copy.deepcopy(events[4])
            pause.update(id="pause_end", cause=None, positions=[])
            pause["changes"] = {key: [] for key in pause["changes"]}
            pause["at"]["wall_s"] = str(Decimal(pause["at"]["wall_s"]) + 5)
            for event in events[5:]:
                event["at"]["wall_s"] = str(Decimal(event["at"]["wall_s"]) + 5)
            events.insert(5, pause)
        self.edit_events(events_edit)
        def manifest_edit(record):
            execution = record["execution"]
            execution["quiet_periods"][0]["from"] = "pause_end"
            execution["quiet_periods"].append({"from": "b003:observed", "to": "pause_end", **input_state(), "gameplay": "paused"})
            for key in ("construction", "total"):
                execution["timing"][key]["wall_s"] = str(Decimal(execution["timing"][key]["wall_s"]) + 5)
        self.edit_manifest(manifest_edit)
        self.expect("admitted")

    def test_successful_reproduction_can_change_route_timing_and_coordinates(self):
        self.use("reproduced")
        self.edit_manifest(lambda r: r["execution"].pop("coordinates"))
        self.expect("admitted")

    def test_missing_reproduction_target_is_pending(self):
        self.use("reproduced")
        self.expect("pending", "REFERENCE_UNAVAILABLE", references=[])

    def test_mismatched_reproduction_target_hash(self):
        self.use("reproduced")
        self.edit_manifest(lambda r: r["target"].update(sha256="f" * 64))
        self.expect("needs_correction", "HASH_MISMATCH")

    def test_reproduction_below_target_claim(self):
        self.use("reproduced")
        self.edit_events(lambda events: events[-1].update(height_m="1"))
        self.expect("needs_correction", "HEIGHT_CLAIM")

    def test_successful_report_needs_own_execution(self):
        self.use("reproduced")
        self.edit_manifest(lambda r: r.update(execution=None))
        self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_failed_attempt_may_stop_without_hold_or_screenshot(self):
        self.use("failed")
        self.assertIsNone(self.manifest_data()["execution"]["native_save"])
        self.expect("admitted", "EVIDENCE_RULE_DEVIATION")

    def test_failed_complete_attempt_does_not_need_successful_hold(self):
        self.use("reproduced")
        self.edit_manifest(lambda r: r.update(verdict="not_reproduced", evidence_limitations="The actual final hold was too short"))
        self.edit_events(lambda events: events[-1]["at"].update(game_s=str(Decimal(events[-2]["at"]["game_s"]) + 1)))
        def edit(record):
            timing = record["execution"]["timing"]
            timing["hold"]["game_s"] = "1"
            timing["total"]["game_s"] = str(Decimal(timing["construction"]["game_s"]) + 1)
        self.edit_manifest(edit)
        self.expect("admitted", "EVIDENCE_RULE_DEVIATION")

    def test_partial_report_still_requires_both_clocks(self):
        self.use("failed")
        self.edit_events(lambda events: events[1]["at"].pop("wall_s"))
        self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_partial_trace_cannot_fabricate_completed_durations(self):
        self.use("failed")
        self.edit_manifest(lambda r: r["execution"]["timing"].update(hold={"wall_s": "30", "game_s": "30"}))
        self.expect("needs_correction", "TIMELINE_INCONSISTENT")

    def test_inconclusive_report_may_explain_missing_trace(self):
        self.use("inconclusive")
        self.expect("admitted")

    def test_conflicting_reports_do_not_overwrite_each_other(self):
        before = (self.fixtures / "reproduced" / "report.json").read_bytes()
        self.use("failed")
        self.expect("admitted")
        self.assertEqual(before, (self.fixtures / "reproduced" / "report.json").read_bytes())
        self.assertEqual(self.manifest_data()["verdict"], "not_reproduced")

    def test_revision_is_a_separate_immutable_record(self):
        self.use("revision")
        self.expect("admitted")

    def test_reusing_an_existing_id_for_different_bytes_is_rejected(self):
        self.edit_manifest(lambda r: r.update(title="[DEMO] Changed content with reused identity"))
        self.expect("needs_correction", "IDENTITY_CONFLICT", references=[self.fixtures / "submission"])

    def test_equivalent_new_submission_id_is_allowed(self):
        self.edit_manifest(lambda r: r.update(id=uid(100)))
        self.expect("admitted", references=[self.fixtures / "submission"])

    def test_withdrawal_keeps_original_record(self):
        self.use("withdrawal")
        self.expect("admitted", "ATTRIBUTION_UNVERIFIED")
        self.assertTrue((self.fixtures / "reproduced" / "report.json").is_file())

    def test_missing_ruleset_is_pending(self):
        self.edit_manifest(lambda r: r["ruleset"].update(id="unknown"))
        self.expect("pending", "UNKNOWN_RULESET")

    def test_missing_start_class_is_not_a_silent_default(self):
        self.edit_artifact("start.json", lambda start: start.update(start_class="unsupported-start"))
        self.expect("needs_correction", "RULE_VIOLATION")

    def test_ruleset_hash_mismatch_is_not_silently_replaced(self):
        self.edit_manifest(lambda r: r["ruleset"].update(sha256="f" * 64))
        self.expect("needs_correction", "HASH_MISMATCH")

    def test_rules_are_not_hardcoded_into_serialization(self):
        profile = json.loads((HERE / "rulesets" / "corporation-state-300-v1.json").read_text())
        profile.update(id="test-profile-hold-31", hold_game_s="31")
        path = Path(self.case_temp.name) / "profile.json"
        path.write_bytes(json_bytes(profile))
        self.edit_manifest(lambda r: r.update(ruleset={"id": profile["id"], "sha256": sha256(path.read_bytes())}))
        self.expect("needs_correction", "RULE_VIOLATION", rulesets=[path])

    def test_future_version_is_pending(self):
        self.edit_manifest(lambda r: r.update(version="99"))
        self.expect("pending", "UNSUPPORTED_VERSION")

    def test_missing_version_is_a_schema_error(self):
        self.edit_manifest(lambda r: r.pop("version"))
        self.expect("needs_correction", "SCHEMA_MISMATCH")

    def test_guidance_is_data_and_external_evidence_is_not_fetched(self):
        def edit(record):
            record["reproduction_guide"]["notes"][0]["instruction"] = "This text is nonbinding data, never an executable command."
            record["external_evidence"] = [{"url": "https://example.invalid/evidence", "sha256": "0" * 64, "media_type": "text/plain", "description": "No network fetch is authorized by this link"}]
        self.edit_manifest(edit)
        with patch("urllib.request.urlopen", side_effect=AssertionError("Must not fetch")):
            self.expect("admitted", "EXTERNAL_EVIDENCE_UNCHECKED")

    def test_generator_refuses_to_overwrite_existing_trial(self):
        with self.assertRaises(FileExistsError):
            build_trial(self.fixtures)

    def test_discovery_links_and_schema_roots_resolve_locally(self):
        entry = json.loads((HERE / "discovery.json").read_text())
        self.assertFalse(entry["publication_available"])
        for name in ("entry_document", "semantic_specification", "schema"):
            self.assertTrue((HERE / entry[name]).is_file(), name)
        for profile in entry["rulesets"]:
            self.assertTrue((HERE / profile).is_file())
        for fragment in entry["schema_definitions"].values():
            self.assertIn(fragment.removeprefix("#/$defs/"), SCHEMA["$defs"])

    def test_real_jpeg_decoding(self):
        # Produce a tiny test image in memory, never native-game evidence.
        environment = {k: os.environ[k] for k in ("PATH", "LANG", "NODE_PATH", "PLAYWRIGHT_BROWSERS_PATH") if k in os.environ}
        environment.setdefault("NODE_PATH", "/opt/peopletest-playwright/runner/node_modules")
        environment.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/peopletest-playwright/browsers")
        script = """
const {chromium} = require('playwright');
(async () => {
 const browser = await chromium.launch({headless:true});
 try {
  const context = await browser.newContext({serviceWorkers:'block'});
  await context.route('**/*', route => route.abort());
  const page = await context.newPage();
  const value = await page.evaluate(() => {
   const canvas = document.createElement('canvas'); canvas.width=2; canvas.height=2;
   return canvas.toDataURL('image/jpeg').split(',')[1];
  });
  process.stdout.write(value);
 } finally { await browser.close(); }
})();
"""
        process = subprocess.run(["node", "-e", script], env=environment, capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        raw = base64.b64decode(process.stdout, validate=True)
        self.assertEqual(self.decoder(raw, "jpeg")[0], "ok")

    def test_cli_exit_codes_and_no_mutation(self):
        before = {p.relative_to(self.case): p.read_bytes() for p in self.case.rglob("*") if p.is_file()}
        process = subprocess.run(["python3", "-B", "-m", "arena_contract", "validate", str(self.case)], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(process.returncode, 1, process.stderr)
        self.assertEqual(json.loads(process.stdout)["status"], "needs_correction")
        self.assertEqual(before, {p.relative_to(self.case): p.read_bytes() for p in self.case.rglob("*") if p.is_file()})
        self.use("inconclusive")
        process = subprocess.run(["python3", "-B", "-m", "arena_contract", "validate", str(self.case), "--allow-demo"], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(process.returncode, 2, process.stderr)
        self.assertEqual(json.loads(process.stdout)["status"], "pending")
        process = subprocess.run(["python3", "-B", "-m", "arena_contract", "validate", str(self.case), "--allow-demo", "--reference", str(self.fixtures / "submission")], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["status"], "admitted")


if __name__ == "__main__":
    unittest.main()
