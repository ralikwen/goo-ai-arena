import copy
import hashlib
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from arena_contract.fixtures import build_trial, uid
from arena_contract.validator import BrowserDecoder, validate_bundle
from arena_platform import ci
from arena_platform.client import bundle_files, git_hash, submit
from arena_platform.core import (PolicyError, authorization, data_delta, digest, encode,
                                 publication_plan, render_catalog)
from arena_platform.export import export_files
from arena_platform.github import APIError, GitHub

ROOT = Path(__file__).resolve().parents[2]
BASE, HEAD, CODE = "a" * 40, "b" * 40, "a" * 40
AUTHOR = {"id": 7732368, "login": "ralikwen"}


def entry(path, raw=b"data", mode="100644", kind="blob"):
    return {"path": path, "sha": git_hash(raw), "mode": mode, "type": kind}


def pr():
    return {"number": 1, "user": copy.deepcopy(AUTHOR), "state": "open", "draft": False,
            "head": {"sha": HEAD}, "base": {"ref": "main", "repo": {"full_name": ci.CONFIG["repository"]}},
            "created_at": "2026-09-13T01:00:00Z"}


class FakeGitHub:
    repository = ci.CONFIG["repository"]
    server_time = "2026-09-13T02:00:00Z"

    def __init__(self, files):
        self.main = BASE
        self.compare_base = BASE
        self.pr = pr()
        self.raw = {git_hash(raw): raw for raw in files.values()}
        self.trees = {BASE: {}, HEAD: {path: entry(path, raw) for path, raw in files.items()}}
        self.commits = 0
        self.writes = []
        self.lose_ref_response = False
        self.change_head_before_advance = False

    def tree(self, sha):
        return copy.deepcopy(self.trees[sha])

    def blob(self, sha):
        return self.raw[sha]

    def get(self, path):
        if path == "/git/ref/heads/main":
            return {"object": {"sha": self.main}}
        if path == "/pulls/1":
            return copy.deepcopy(self.pr)
        if path.startswith("/compare/"):
            return {"merge_base_commit": {"sha": self.compare_base}}
        raise AssertionError(path)

    def commit_files(self, parent, files, message, *, blobs=None):
        self.commits += 1
        sha = hashlib.sha1(str(self.commits).encode()).hexdigest()
        tree = self.tree(parent)
        for path, raw in files.items():
            self.raw[git_hash(raw)] = raw
            tree[path] = entry(path, raw)
        for path, blob in (blobs or {}).items():
            tree[path] = {"path": path, "sha": blob, "mode": "100644", "type": "blob"}
        self.trees[sha] = tree
        if self.change_head_before_advance:
            self.pr["head"]["sha"] = "c" * 40
        return sha

    def advance(self, branch, commit):
        self.main = commit
        if self.lose_ref_response:
            self.lose_ref_response = False
            raise APIError("lost_response")

    def request(self, method, path, value=None):
        self.writes.append((method, path, value))
        if path == "/pulls/1" and method == "PATCH":
            self.pr.update(value)
        return {"id": 123, "html_url": "https://github.com/example"}

    def pages(self, path):
        return iter([])


class PlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "var").mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix="arena-platform-tests-", dir=ROOT / "var")
        cls.work = Path(cls.temp.name)
        cls.fixtures = cls.work / "fixtures"
        build_trial(cls.fixtures)
        cls.decoder = BrowserDecoder()
        cls.record, cls.manifest, cls.files = bundle_files(cls.fixtures / "submission")
        cls.admission = validate_bundle(cls.fixtures / "submission", allow_demo=True, decoder=cls.decoder)
        assert cls.admission["status"] == "admitted", cls.admission

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.case = tempfile.TemporaryDirectory(prefix="case-", dir=self.work)
        self.path = Path(self.case.name)
        self.context = {"repository": ci.CONFIG["repository"], "branch": "main", "pr_number": 1,
                        "base_sha": BASE, "head_sha": HEAD, "trusted_sha": CODE,
                        "submitted_by": copy.deepcopy(AUTHOR), "request_opened_at": pr()["created_at"],
                        "record_id": uid(1), "manifest_path": f"records/{uid(1)}/submission.json",
                        "blobs": {path: git_hash(raw) for path, raw in self.files.items()}}
        self.result = {"format": "goo-ai-arena.check", "version": "0.1", "status": "admitted",
                       "record": {"id": uid(1), "sha256": digest(self.manifest)},
                       "admission": copy.deepcopy(self.admission), "platform_issues": [], "context": self.context}
        self.environment = {"GITHUB_REPOSITORY": ci.CONFIG["repository"], "GITHUB_SHA": CODE,
                            "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_EVENT_NAME": "workflow_dispatch",
                            "GITHUB_REF": "refs/heads/main", "ARENA_PR_NUMBER": "1",
                            "GITHUB_EVENT_PATH": str(self.path / "event.json")}
        (self.path / "event.json").write_bytes(b"{}")

    def tearDown(self):
        self.case.cleanup()

    def policy(self, code, function, *args):
        with self.assertRaises(PolicyError) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, code)

    def test_single_data_bundle_delta(self):
        record_id, paths, manifest = data_delta({}, {p: entry(p, raw) for p, raw in self.files.items()})
        self.assertEqual(record_id, uid(1))
        self.assertEqual(set(paths), set(self.files))
        self.assertEqual(manifest, self.context["manifest_path"])

    def test_api_compare_ellipsis_is_not_parent_traversal(self):
        client = GitHub(ci.CONFIG["repository"], "synthetic-test-token-not-valid")
        with patch.object(client.opener, "open", side_effect=urllib.error.URLError("test transport unavailable")):
            with self.assertRaises(APIError):
                client.get(f"/compare/{BASE}...{HEAD}")
        with self.assertRaises(ValueError):
            client.get("/../another-repository")

    def test_code_changes_never_auto_admit(self):
        self.policy("MAINTAINER_REVIEW", data_delta, {}, {"arena_contract/validator.py": entry("arena_contract/validator.py")})

    def test_existing_record_cannot_be_edited_or_deleted(self):
        path = self.context["manifest_path"]
        for head in ({}, {path: entry(path, b"changed")}):
            self.policy("IMMUTABLE_RECORD", data_delta, {path: entry(path)}, head)

    def test_symlink_executable_submodule_rejected(self):
        path = self.context["manifest_path"]
        for mode, kind in (("120000", "blob"), ("100755", "blob"), ("160000", "commit")):
            self.policy("UNSAFE_GIT_ENTRY", data_delta, {}, {path: entry(path, mode=mode, kind=kind)})

    def test_paths_cannot_escape_bundle(self):
        for path in (f"records/{uid(1)}/../receipt.json", f"records/{uid(1)}/.git/config", f"records/{uid(1)}/A.py"):
            self.policy("MAINTAINER_REVIEW", data_delta, {}, {path: entry(path)})

    def test_maintainer_review_explains_protected_content_not_tower_ranking(self):
        with self.assertRaises(PolicyError) as caught:
            data_delta({}, {"arena_contract/validator.py": entry("arena_contract/validator.py")})
        error = caught.exception
        self.assertEqual(error.status, "maintainer_review")
        self.assertIn("protected repository content", str(error))
        self.assertIn("unrelated to the tower's height or ranking", str(error))
        self.assertNotIn("non-record", str(error))

    def test_one_uuid_per_request(self):
        head = {f"records/{uid(i)}/submission.json": entry(f"records/{uid(i)}/submission.json") for i in (1, 2)}
        self.policy("ONE_RECORD_PER_REQUEST", data_delta, {}, head)

    def test_equivalent_tower_with_new_uuid_is_not_deduplicated(self):
        ancestor = {path: entry(path, raw) for path, raw in self.files.items()}
        head = copy.deepcopy(ancestor)
        for path, raw in self.files.items():
            new_path = path.replace(uid(1), uid(7))
            head[new_path] = entry(new_path, raw)
        record_id, paths, _ = data_delta(ancestor, head)
        self.assertEqual(record_id, uid(7))
        self.assertEqual(len(paths), len(self.files))

    def test_exactly_one_top_level_manifest(self):
        path = f"records/{uid(1)}/nested/submission.json"
        self.policy("MANIFEST_COUNT", data_delta, {}, {path: entry(path)})

    def test_all_admitted_conditions_before_publication(self):
        self.assertEqual(publication_plan(self.result, pr(), BASE, {}, {}), "publish")

    def test_stale_head_rejected(self):
        request = pr()
        request["head"]["sha"] = "c" * 40
        self.policy("STALE_HEAD", publication_plan, self.result, request, BASE, {}, {})

    def test_stale_base_rejected(self):
        self.policy("STALE_BASE", publication_plan, self.result, pr(), "c" * 40, {}, {})

    def test_closed_or_draft_request_not_published(self):
        for change in ({"state": "closed"}, {"draft": True}):
            request = pr()
            request.update(change)
            self.policy("REQUEST_NOT_OPEN", publication_plan, self.result, request, BASE, {}, {})

    def test_changed_account_not_published(self):
        request = pr()
        request["user"]["id"] = 999
        self.policy("IDENTITY_CHANGED", publication_plan, self.result, request, BASE, {}, {})

    def test_pending_result_never_published(self):
        self.result["status"] = "pending"
        self.policy("NOT_ADMITTED", publication_plan, self.result, pr(), BASE, {}, {})

    def test_publication_without_receipt_is_not_overwritten(self):
        self.policy("RECEIPT_MISSING", publication_plan, self.result, pr(), BASE, {self.context["manifest_path"]: entry(self.context["manifest_path"])}, {})

    def receipt(self, record=None):
        record = record or self.record
        return {"record": {"id": record["id"], "sha256": digest(self.manifest)},
                "manifest_path": f"records/{record['id']}/submission.json", "submitted_at": "2026-09-13T02:00:00Z",
                "submitted_by": copy.deepcopy(AUTHOR)}

    def test_retry_returns_original_receipt_even_if_base_advanced(self):
        receipts = {uid(1): self.receipt()}
        tree = {path: entry(path, raw) for path, raw in self.files.items()}
        self.assertEqual(publication_plan(self.result, pr(), "c" * 40, tree, receipts), "already_published")

    def test_retry_identity_collision_rejected(self):
        receipt = self.receipt()
        receipt["record"]["sha256"] = "f" * 64
        self.policy("IDENTITY_COLLISION", publication_plan, self.result, pr(), BASE, {}, {uid(1): receipt})

    def test_api_enforces_configured_public_or_private_visibility(self):
        for visibility in ("public", "private"):
            for actual in (True, False, None):
                with self.subTest(visibility=visibility, actual=actual):
                    with patch.dict(os.environ, {"GITHUB_REPOSITORY": ci.CONFIG["repository"], "GH_TOKEN": "test-only"}), patch.object(ci, "GitHub") as client, patch.dict(ci.CONFIG, {"visibility": visibility}):
                        client.return_value.get.return_value = {"private": actual}
                        if actual is (visibility == "private"):
                            self.assertIs(ci.api(), client.return_value)
                        else:
                            self.policy("REPOSITORY_VISIBILITY_MISMATCH", ci.api)

    def test_api_rejects_bad_visibility_and_wrong_repository(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": ci.CONFIG["repository"], "GH_TOKEN": "test-only"}), patch.object(ci, "GitHub") as client, patch.dict(ci.CONFIG, {"visibility": "anything"}):
            client.return_value.get.return_value = {"private": False}
            self.policy("INVALID_VISIBILITY", ci.api)
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "unrelated/repository"}):
            self.policy("WRONG_REPOSITORY", ci.api)

    def test_retry_changed_artifact_rejected(self):
        tree = {path: entry(path, raw) for path, raw in self.files.items()}
        tree[f"records/{uid(1)}/finished.png"]["sha"] = "d" * 40
        self.policy("PUBLISHED_BYTES_CHANGED", publication_plan, self.result, pr(), BASE, tree, {uid(1): self.receipt()})

    def test_uploader_id_not_display_name_controls_withdrawal(self):
        reference = self.receipt()["record"]
        record = {"format": "goo-ai-arena.withdrawal", "target": reference}
        self.policy("NOT_RECORD_UPLOADER", authorization, record, {"id": 999, "login": "ralikwen"}, {uid(1): self.receipt()})
        authorization(record, {"id": AUTHOR["id"], "login": "renamed-account"}, {uid(1): self.receipt()})

    def test_uploader_required_for_revision(self):
        record = {"format": "goo-ai-arena.submission", "revises": self.receipt()["record"]}
        self.policy("NOT_RECORD_UPLOADER", authorization, record, {"id": 999}, {uid(1): self.receipt()})

    def test_report_can_come_from_another_account(self):
        authorization({"format": "goo-ai-arena.reproduction-report", "target": self.receipt()["record"]}, {"id": 999}, {uid(1): self.receipt()})

    def test_unknown_ownership_reference_pending(self):
        self.policy("REFERENCE_UNAVAILABLE", authorization, {"revises": self.receipt()["record"]}, AUTHOR, {})

    def test_presentation_escapes_submitted_markup_and_shows_clocks(self):
        record = copy.deepcopy(self.record)
        record["title"] = '[DEMO] <script>alert(1)</script> ![x](https://example.com/tracker)'
        record["about"]["background"] = "I learned that teaching AI is hard."
        files = render_catalog({uid(1): record}, {uid(1): self.receipt()})
        page = files[f"catalog/{uid(1)}.md"].decode()
        self.assertNotIn("<script>", page)
        self.assertNotIn("![x](", page)
        self.assertIn("Wall seconds", page)
        self.assertIn("Game seconds", page)
        self.assertIn("Note and tooling", page)
        self.assertIn(r"Note: I learned that teaching AI is hard\.", page)
        self.assertNotIn("Background:", page)
        self.assertIn("finished.png", page)
        self.assertIn("save/pers3.dat", page)
        self.assertIn("not restorable", page)
        index = json.loads(files["catalog/index.json"])
        self.assertEqual(index["records"][0]["native_save"], record["execution"]["native_save"])
        self.assertEqual(index["records"][0]["contract_version"], "0.2")

    def test_save_restore_instructions_are_escaped_not_executed(self):
        record = copy.deepcopy(self.record)
        record["execution"]["native_save"]["restore_instructions"] = '<script>alert(1)</script> ![tracker](https://example.invalid/pixel)'
        files = render_catalog({uid(1): record}, {uid(1): self.receipt()})
        page = files[f"catalog/{uid(1)}.md"].decode()
        self.assertNotIn("<script>", page)
        self.assertNotIn("![tracker](", page)
        self.assertIn("untrusted submitted data", page)

    def test_catalogue_title_guides_and_real_image_caption(self):
        record = copy.deepcopy(self.record)
        record["purpose"] = "competition"
        record["title"] = "Ralikwen — It's a tower & a <test>"
        record["execution"]["image"]["caption"] = "Full view after reload; camera only."
        record["files"].extend([
            {"path": name, "format": "markdown", "sha256": "a" * 64}
            for name in ("readme.md", "rebuild.md", "rebuild-steps.md", "setup.md", "https://evil.invalid/page")])
        files = render_catalog({uid(1): record}, {uid(1): self.receipt()})
        page = files[f"catalog/{uid(1)}.md"].decode()
        self.assertIn("# Ralikwen — It's a tower &amp; a &lt;test&gt;", page)
        self.assertNotIn("&#x27;", page)
        self.assertNotIn("<test>", page)
        for name in ("readme.md", "rebuild.md", "rebuild-steps.md", "setup.md"):
            self.assertIn(f"(../records/{uid(1)}/{name})", page)
        self.assertNotIn("evil.invalid", page)
        self.assertIn("Full view after reload; camera only", page)
        self.assertNotIn("Demo placeholders", page)

    def test_revision_chain_ranks_only_latest_and_preserves_history(self):
        records, receipts = {}, {}
        previous = None
        for number in (1, 7, 8):
            record = copy.deepcopy(self.record)
            record.update(id=uid(number), purpose="competition", revises=previous)
            receipt = copy.deepcopy(self.receipt())
            receipt["record"] = {"id": record["id"], "sha256": digest(encode(record))}
            receipt["manifest_path"] = f"records/{record['id']}/submission.json"
            records[record["id"]], receipts[record["id"]] = record, receipt
            previous = receipt["record"]
        files = render_catalog(records, receipts)
        listing = files["catalog/README.md"].decode()
        self.assertNotIn(f"({uid(1)}.md)", listing)
        self.assertNotIn(f"({uid(7)}.md)", listing)
        self.assertIn(f"({uid(8)}.md)", listing)
        for old in (uid(1), uid(7)):
            self.assertIn(f"[Latest revision]({uid(8)}.md)", files[f"catalog/{old}.md"].decode())
        index = json.loads(files["catalog/index.json"])
        self.assertEqual(index["official_record_count"], 1)
        self.assertEqual(len(index["records"]), 3)
        # Withdrawing the latest version must not resurrect superseded claims.
        records[uid(9)] = {"id": uid(9), "version": "0.2", "format": "goo-ai-arena.withdrawal", "purpose": "competition",
                           "target": receipts[uid(8)]["record"], "reason": "Withdrawn", "files": []}
        receipts[uid(9)] = copy.deepcopy(receipts[uid(8)])
        receipts[uid(9)]["record"] = {"id": uid(9), "sha256": "b" * 64}
        files = render_catalog(records, receipts)
        self.assertEqual(json.loads(files["catalog/index.json"])["official_record_count"], 0)

    def test_historical_catalog_record_does_not_acquire_save_compliance(self):
        record = copy.deepcopy(self.record)
        record["version"] = "0.1"
        record["execution"].pop("native_save")
        files = render_catalog({uid(1): record}, {uid(1): self.receipt()})
        self.assertIn("no mandatory native-save check", files[f"catalog/{uid(1)}.md"].decode())
        entry = json.loads(files["catalog/index.json"])["records"][0]
        self.assertEqual(entry["contract_version"], "0.1")
        self.assertIsNone(entry["native_save"])

    def test_process_claim_is_displayed_as_attribution_not_verification(self):
        record = copy.deepcopy(self.record)
        record["purpose"] = "competition"
        record["execution"]["process_claim"] = {
            "mode": "human_and_machine",
            "description": '[DEMO] Human supervision <script>alert(1)</script> ![tracker](https://example.invalid/pixel)'}
        files = render_catalog({uid(1): record}, {uid(1): self.receipt()})
        page = files[f"catalog/{uid(1)}.md"].decode()
        self.assertIn("Discovery and building (self-declared)", page)
        self.assertIn("including human oversight", page)
        self.assertIn("not independently verified", page)
        self.assertNotIn("<script>", page)
        self.assertNotIn("![tracker](", page)
        self.assertIn("including human oversight", files["catalog/README.md"].decode())
        index = json.loads(files["catalog/index.json"])
        self.assertEqual(index["records"][0]["process_claim"], record["execution"]["process_claim"])

    def test_missing_historical_process_is_not_inferred_from_identity(self):
        record = copy.deepcopy(self.record)
        record["version"] = "0.1"
        record["execution"].pop("process_claim")
        record["creators"][0]["kind"] = "ai"
        files = render_catalog({uid(1): record}, {uid(1): self.receipt()})
        page = files[f"catalog/{uid(1)}.md"].decode()
        self.assertIn("Not declared in this historical entry", page)
        self.assertNotIn("Fully machine discovery", page)
        index = json.loads(files["catalog/index.json"])
        self.assertIsNone(index["records"][0]["process_claim"])

    def test_reports_and_withdrawals_retained_not_new_tower_claims(self):
        records, receipts = {}, {}
        for name in ("submission", "reproduced", "failed", "inconclusive", "revision", "withdrawal"):
            record, raw, _ = bundle_files(self.fixtures / name)
            records[record["id"]] = record
            receipts[record["id"]] = {"record": {"id": record["id"], "sha256": digest(raw)}, "manifest_path": next(p.name for p in (self.fixtures / name).iterdir() if p.name in {"submission.json", "report.json", "withdrawal.json"}), "submitted_at": "2026-09-13T02:00:00Z", "submitted_by": AUTHOR}
        files = render_catalog(records, receipts)
        index = json.loads(files["catalog/index.json"])
        self.assertEqual(index["official_record_count"], 0)
        self.assertEqual(len(index["records"]), 6)
        tower = next(e for e in index["records"] if e["record"]["id"] == uid(1))
        self.assertEqual({r["verdict"] for r in tower["reports"]}, {"reproduced", "not_reproduced", "inconclusive"})
        self.assertTrue(next(r for r in tower["reports"] if r["verdict"] == "reproduced")["withdrawn"])
        overview = files["catalog/README.md"].decode()
        self.assertNotIn(f"({uid(2)}.md)", overview)

    def test_export_omits_research_credentials_history_and_records(self):
        files = export_files(ROOT)
        self.assertIn(".github/workflows/admission.yml", files)
        self.assertFalse(any(path.startswith(("var/", "results/", "vendor/", "scripts/", ".git/", "records/", "receipts/")) for path in files))
        self.assertIn("docs/community-replay-spec-v0.2.md", files)
        discovery = json.loads(files["discovery.json"])
        self.assertEqual(discovery["contract_version"], "0.2")
        self.assertIn("native_game_save", discovery["required_success_evidence"])
        for path in ("discovery.json", "arena_contract/discovery.json"):
            claim = json.loads(files[path])["process_claim"]
            self.assertEqual(claim["field"], "execution.process_claim")
            self.assertEqual(claim["modes"], ["machine_only", "human_and_machine", "human_only"])
            self.assertTrue(claim["description_required"])
        for field in ("entry", "participation", "security", "contract", "schema", "receipt_schema", "semantics", "catalogue", "presentation", "examples"):
            self.assertIn(discovery[field], files)

    def test_export_is_reusable_without_development_template_directory(self):
        files = export_files(ROOT)
        exported = self.path / "exported"
        for relative, raw in files.items():
            target = exported / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        self.assertEqual(export_files(exported), files)

    def test_public_facing_entry_is_clear_without_opening_private_trial(self):
        files = export_files(ROOT)
        opening = files["README.md"].decode()
        self.assertTrue(opening.startswith("# Goo AI Arena\n"))
        self.assertIn("How high can your AI go?", opening)
        self.assertNotIn("Height determines ranking, not admission", opening)
        self.assertNotIn("Similar towers are welcome", opening)
        self.assertIn("run the World of Goo game binary", opening)
        self.assertNotIn("GooTower game binary", opening)
        self.assertIn("https://www.gog.com/en/game/world_of_goo", opening)
        self.assertIn("legal game-building steps", opening)
        self.assertIn("The competitor's AI runs the game", opening)
        self.assertIn("native save", opening)
        self.assertNotIn("competition submissions are not open yet", opening)
        self.assertNotIn("Public launch is in preparation", opening)
        self.assertNotIn("private test environment", opening)
        self.assertNotIn("docs/trial-results.md", opening)
        self.assertNotIn("--allow-demo", opening)
        discovery = json.loads(files["discovery.json"])
        self.assertEqual(discovery["building_workflow"]["game"], "World of Goo")
        self.assertIn("not the submission platform", discovery["building_workflow"]["execution_location"])
        self.assertFalse(discovery["admission_policy"]["must_beat_previous_height"])
        self.assertFalse(discovery["admission_policy"]["must_be_a_new_design"])
        self.assertIn("protected repository content", discovery["outcomes"]["maintainer_review"])
        self.assertNotIn("Non-record", discovery["outcomes"]["maintainer_review"])
        config = json.loads(files["arena_platform/config.json"])
        self.assertFalse(config["demo_only"])
        self.assertEqual(config["stage"], "competition")
        self.assertEqual(discovery["stage"], config["stage"])
        self.assertEqual(discovery["repository"], config["repository"])

    def test_catalogue_keeps_shorter_and_equal_height_submissions(self):
        records, receipts = {}, {}
        for number, height in ((1, "12.3"), (7, "5.0"), (8, "12.3")):
            record = copy.deepcopy(self.record)
            record["purpose"] = "competition"
            record["id"] = uid(number)
            record["claim"]["height_m"] = height
            records[record["id"]] = record
            receipt = copy.deepcopy(self.receipt())
            receipt["record"] = {"id": record["id"], "sha256": digest(encode(record))}
            receipt["manifest_path"] = f"records/{record['id']}/submission.json"
            receipts[record["id"]] = receipt
        files = render_catalog(records, receipts)
        catalogue = files["catalog/README.md"].decode()
        for record_id in records:
            self.assertIn(f"({record_id}.md)", catalogue)
        self.assertIn("Height determines ranking, not admission", catalogue)
        self.assertEqual(len(json.loads(files["catalog/index.json"])["records"]), 3)

    def test_feedback_does_not_mutate_admission_or_platform_issues(self):
        fake = FakeGitHub(self.files)
        self.result["admission"]["errors"] = [{"code": "TEST_ERROR", "retryable": False}]
        before = copy.deepcopy(self.result)
        with patch.dict(os.environ, self.environment):
            ci.feedback(fake, 1, self.result)
        self.assertEqual(self.result, before)

    def run_publish(self, fake):
        result_path, output = self.path / "result.json", self.path / "publication.json"
        result_path.write_bytes(encode(self.result))
        with patch.dict(os.environ, self.environment), patch.object(ci, "api", return_value=fake), patch.dict(ci.CONFIG, {"demo_only": True}):
            ci.publish(result_path, output)
        return json.loads(output.read_text())

    def test_atomic_publication_and_fresh_client_retry(self):
        fake = FakeGitHub(self.files)
        result = self.run_publish(fake)
        self.assertEqual(result["status"], "published", result)
        self.assertEqual(fake.commits, 1)
        receipt_path = f"receipts/{uid(1)}.json"
        self.assertIn(receipt_path, fake.trees[fake.main])
        self.assertIn("catalog/index.json", fake.trees[fake.main])
        save = self.record["execution"]["native_save"]
        saved_blob = fake.tree(fake.main)[f"records/{uid(1)}/{save['path']}"]
        self.assertEqual(fake.blob(saved_blob["sha"]), (self.fixtures / "submission" / save["path"]).read_bytes())
        reply = submit(fake, self.fixtures / "submission")
        self.assertEqual(reply["status"], "already_published")
        self.assertEqual(reply["receipt"]["submitted_at"], fake.server_time)
        self.assertEqual(fake.commits, 1)

    def test_lost_ref_response_recovered_without_second_commit(self):
        fake = FakeGitHub(self.files)
        fake.lose_ref_response = True
        first = self.run_publish(fake)
        self.assertEqual(first["status"], "pending")
        self.assertNotEqual(fake.main, BASE)
        second = self.run_publish(fake)
        self.assertEqual(second["status"], "already_published", second)
        self.assertEqual(fake.commits, 1)

    def test_head_change_during_commit_creation_does_not_advance_main(self):
        fake = FakeGitHub(self.files)
        fake.change_head_before_advance = True
        result = self.run_publish(fake)
        self.assertEqual(result["status"], "pending")
        self.assertEqual(fake.main, BASE)

    def test_missing_checker_result_stays_pending(self):
        fake = FakeGitHub(self.files)
        output = self.path / "publication.json"
        with patch.dict(os.environ, self.environment), patch.object(ci, "api", return_value=fake):
            ci.publish(self.path / "absent.json", output)
        self.assertEqual(json.loads(output.read_text())["status"], "pending")
        self.assertEqual(fake.commits, 0)

    def test_mismatched_admission_record_does_not_publish(self):
        fake = FakeGitHub(self.files)
        self.result["admission"]["record"]["sha256"] = "d" * 64
        result = self.run_publish(fake)
        self.assertEqual(result["status"], "pending")
        self.assertEqual(fake.commits, 0)

    def test_prepare_check_real_decoder_and_publisher(self):
        fake = FakeGitHub(self.files)
        prepared, result_path = self.path / "prepared", self.path / "checked.json"
        with patch.dict(os.environ, self.environment), patch.object(ci, "api", return_value=fake), patch.dict(ci.CONFIG, {"demo_only": True}):
            ci.prepare(prepared)
            ci.check(prepared, result_path)
        result = json.loads(result_path.read_text())
        self.assertEqual(result["status"], "admitted", result)
        self.result = result
        self.assertEqual(self.run_publish(fake)["status"], "published")

    def test_competition_policy_rejects_demo_at_check_and_publish(self):
        fake = FakeGitHub(self.files)
        prepared, checked = self.path / "prepared", self.path / "checked.json"
        with patch.dict(os.environ, self.environment), patch.object(ci, "api", return_value=fake):
            ci.prepare(prepared)
            ci.check(prepared, checked)
            result = json.loads(checked.read_text())
            self.assertEqual(result["status"], "needs_correction")
            self.assertIn("DEMO_NOT_ALLOWED", {e["code"] for e in result["admission"]["errors"]})
            incoming, output = self.path / "incoming.json", self.path / "published.json"
            incoming.write_bytes(encode(self.result))
            ci.publish(incoming, output)
        self.assertEqual(json.loads(output.read_text())["status"], "needs_correction")
        self.assertEqual(fake.commits, 0)

    def test_competition_publisher_accepts_checked_competition_record(self):
        # Synthetic bytes stay inside this isolated unit test; never submit them live.
        record = copy.deepcopy(self.record)
        record["purpose"] = "competition"
        record["claim_kind"] = "reported_execution"
        record["execution"]["image"]["origin"] = "game_screenshot"
        record["execution"]["native_save"]["origin"] = "game_save"
        raw = encode(record)
        files = dict(self.files)
        files[self.context["manifest_path"]] = raw
        self.result["record"]["sha256"] = digest(raw)
        self.result["admission"]["record"] = copy.deepcopy(self.result["record"])
        self.context["blobs"][self.context["manifest_path"]] = git_hash(raw)
        fake = FakeGitHub(files)
        incoming, output = self.path / "incoming.json", self.path / "published.json"
        incoming.write_bytes(encode(self.result))
        with patch.dict(os.environ, self.environment), patch.object(ci, "api", return_value=fake):
            ci.publish(incoming, output)
        self.assertEqual(json.loads(output.read_text())["status"], "published", output.read_text())
        index = json.loads(fake.blob(fake.tree(fake.main)["catalog/index.json"]["sha"]))
        self.assertEqual(index["official_record_count"], 1)
        self.assertEqual(index["stage"], "competition")

    def test_linked_record_chain_preserves_reference_manifest_names(self):
        fake = FakeGitHub(self.files)
        self.assertEqual(self.run_publish(fake)["status"], "published")
        for name in ("reproduced", "failed", "inconclusive", "revision", "withdrawal"):
            with self.subTest(record=name):
                _, _, files = bundle_files(self.fixtures / name)
                fake.compare_base = fake.main
                fake.pr["state"] = "open"
                fake.trees[HEAD] = fake.tree(fake.main)
                for path, raw in files.items():
                    fake.raw[git_hash(raw)] = raw
                    fake.trees[HEAD][path] = entry(path, raw)
                prepared, result_path = self.path / name, self.path / (name + ".json")
                with patch.dict(os.environ, self.environment), patch.object(ci, "api", return_value=fake), patch.dict(ci.CONFIG, {"demo_only": True}):
                    ci.prepare(prepared)
                    ci.check(prepared, result_path)
                self.result = json.loads(result_path.read_text())
                self.assertEqual(self.result["status"], "admitted", self.result)
                self.assertTrue((prepared / "references" / uid(1) / "submission.json").exists())
                self.assertEqual(self.run_publish(fake)["status"], "published")
        catalogue = json.loads(fake.blob(fake.tree(fake.main)["catalog/index.json"]["sha"]))
        self.assertEqual(len(catalogue["records"]), 6)


if __name__ == "__main__":
    unittest.main()
