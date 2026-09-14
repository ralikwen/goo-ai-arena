"""Trusted-base workflow: prepare with read access, check without token, publish separately."""

from __future__ import annotations

import argparse
import json
import os
import re
import traceback
from pathlib import Path

from .core import (FILE, UUID, PolicyError, authorization, data_delta, digest, encode,
                   publication_plan, render_catalog)
from .github import APIError, GitHub

HERE = Path(__file__).parent
CONFIG = json.loads((HERE / "config.json").read_text())
COMMENT_TAG = "<!-- goo-ai-arena:admission-v1 -->"


def api():
    if os.environ.get("GITHUB_REPOSITORY") != CONFIG["repository"]:
        raise PolicyError("WRONG_REPOSITORY", "The workflow repository differs from its trusted configuration.", "pending")
    client = GitHub(CONFIG["repository"], os.environ["GH_TOKEN"])
    metadata = client.get("")
    visibility = CONFIG.get("visibility", "private")
    if visibility not in ("public", "private"):
        raise PolicyError("INVALID_VISIBILITY", "The trusted visibility configuration is invalid.", "pending")
    if metadata.get("private") is not (visibility == "private"):
        raise PolicyError("REPOSITORY_VISIBILITY_MISMATCH", "Repository visibility differs from its trusted configuration.", "pending")
    return client


def request_number():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    event_name = os.environ["GITHUB_EVENT_NAME"]
    if event_name == "pull_request_target":
        number = event["number"]
    elif event_name == "issue_comment" and "pull_request" in event["issue"]:
        if event["comment"]["body"].strip() != "/arena recheck":
            raise PolicyError("NOT_A_RECHECK", "This comment is not a recheck request.", "pending")
        number = event["issue"]["number"]
    elif event_name == "workflow_dispatch" and os.environ.get("GITHUB_REF") == "refs/heads/" + CONFIG["branch"]:
        value = os.environ.get("ARENA_PR_NUMBER", "")
        if not re.fullmatch(r"[1-9][0-9]*", value):
            raise PolicyError("BAD_REQUEST_NUMBER", "Supply a positive pull request number.", "pending")
        number = int(value)
    else:
        raise PolicyError("UNSUPPORTED_EVENT", "Use a data PR, /arena recheck, or a dispatch on main.", "pending")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise PolicyError("BAD_REQUEST_NUMBER", "Invalid pull request number.", "pending")
    return number


def registry(api_client, tree):
    receipts, records = {}, {}
    for path, entry in sorted(tree.items()):
        if re.fullmatch(r"receipts/" + UUID + r"\.json", path):
            receipt = json.loads(api_client.blob(entry["sha"]))
            record_id = path.split("/")[-1][:-5]
            if receipt["record"]["id"] != record_id:
                raise PolicyError("REGISTRY_INCONSISTENT", "A receipt has an inconsistent record ID.", "pending")
            manifest_path = receipt["manifest_path"]
            if not FILE.fullmatch(manifest_path) or not manifest_path.startswith(f"records/{record_id}/"):
                raise PolicyError("REGISTRY_INCONSISTENT", "A receipt has an unsafe manifest path.", "pending")
            raw = api_client.blob(tree[manifest_path]["sha"])
            if digest(raw) != receipt["record"]["sha256"]:
                raise PolicyError("REGISTRY_INCONSISTENT", "A published manifest no longer matches its receipt.", "pending")
            receipts[record_id], records[record_id] = receipt, json.loads(raw)
    return receipts, records


def failure(error, context=None):
    if isinstance(error, PolicyError):
        status, code, message = error.status, error.code, str(error)
    else:
        status, code = "pending", "INFRASTRUCTURE_UNAVAILABLE"
        message = "A platform dependency, API, resource or internal check was unavailable. No illegality is inferred; recheck or ask a maintainer."
    diagnostic = {"exception_type": type(error).__name__}
    if isinstance(error, APIError):
        diagnostic["http_status"] = error.status
    frames = traceback.extract_tb(error.__traceback__)
    if frames:
        diagnostic.update(file=Path(frames[-1].filename).name, line=frames[-1].lineno)
    return {"format": "goo-ai-arena.check", "version": "0.1", "status": status,
            "record": None, "context": context, "admission": None,
            "platform_issues": [{"code": code, "message": message, "retryable": status == "pending", "diagnostic": diagnostic}]}


def prepare(destination):
    destination.mkdir(parents=True, exist_ok=False)
    context = None
    try:
        client = api()
        number = request_number()
        pr = client.get(f"/pulls/{number}")
        if pr["base"]["ref"] != CONFIG["branch"] or pr["base"]["repo"]["full_name"] != CONFIG["repository"]:
            raise PolicyError("WRONG_BASE", "Data requests must target this repository's main branch.", "maintainer_review")
        if os.environ["GITHUB_EVENT_NAME"] == "issue_comment":
            event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
            if event["comment"]["user"]["id"] not in [pr["user"]["id"], *CONFIG["maintainer_ids"]]:
                raise PolicyError("RECHECK_NOT_AUTHORIZED", "Only the request author or a configured maintainer can request a recheck.", "pending")
        base_sha = client.get("/git/ref/heads/" + CONFIG["branch"])["object"]["sha"]
        trusted_sha = os.environ["GITHUB_SHA"]
        context = {"repository": CONFIG["repository"], "branch": CONFIG["branch"], "pr_number": number,
                   "base_sha": base_sha, "head_sha": pr["head"]["sha"], "trusted_sha": trusted_sha,
                   "submitted_by": {"id": pr["user"]["id"], "login": pr["user"]["login"]},
                   "request_opened_at": pr["created_at"]}
        base = client.tree(base_sha)
        trusted = base if trusted_sha == base_sha else client.tree(trusted_sha)
        control_paths = {p for p in set(base) | set(trusted)
                         if p.startswith(("arena_contract/", "arena_platform/", ".github/"))}
        if any(base.get(path) != trusted.get(path) for path in control_paths):
            raise PolicyError("STALE_PLATFORM", "Platform code or rules changed; start a new /arena recheck on the current main branch.", "pending")
        comparison = client.get(f"/compare/{base_sha}...{context['head_sha']}")
        ancestor = client.tree(comparison["merge_base_commit"]["sha"])
        head = client.tree(context["head_sha"])
        record_id, paths, manifest = data_delta(ancestor, head)
        context.update(record_id=record_id, manifest_path=manifest,
                       blobs={path: head[path]["sha"] for path in paths})
        bundle = destination / "bundle"
        bundle.mkdir()
        for path in paths:
            relative = FILE.fullmatch(path)["path"]
            target = bundle / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(client.blob(head[path]["sha"]))
        receipts, records = registry(client, base)
        references = destination / "references"
        references.mkdir()
        for record_id, receipt in receipts.items():
            # Exact manifest bytes, not reserialized JSON: record refs hash original bytes.
            target = references / record_id / Path(receipt["manifest_path"]).name
            target.parent.mkdir()
            target.write_bytes(client.blob(base[receipt["manifest_path"]]["sha"]))
        (destination / "receipts.json").write_bytes(encode(receipts))
        (destination / "context.json").write_bytes(encode(context))
    except Exception as error:
        (destination / "preflight-error.json").write_bytes(encode(failure(error, context)))


def check(prepared, result_path):
    context = None
    try:
        if (prepared / "preflight-error.json").exists():
            result = json.loads((prepared / "preflight-error.json").read_text())
        else:
            from arena_contract.validator import parse_json, validate_bundle
            context = json.loads((prepared / "context.json").read_text())
            admission = validate_bundle(prepared / "bundle", allow_demo=CONFIG["demo_only"],
                                        references=sorted((prepared / "references").iterdir()))
            result = {"format": "goo-ai-arena.check", "version": "0.1", "status": admission["status"],
                      "record": admission["record"], "context": context, "admission": admission,
                      "platform_issues": []}
            if admission["status"] == "admitted":
                raw = (prepared / "bundle" / context["manifest_path"].split("/")[-1]).read_bytes()
                record = parse_json(raw)
                if record["id"] != context["record_id"]:
                    raise PolicyError("DIRECTORY_ID_MISMATCH", "The directory UUID must match the manifest UUID.")
                if CONFIG["demo_only"] and record["purpose"] != "demo":
                    raise PolicyError("TRIAL_ONLY", "This disposable trial accepts only explicitly synthetic demo records.")
                receipts = json.loads((prepared / "receipts.json").read_text())
                authorization(record, context["submitted_by"], receipts)
    except Exception as error:
        result = failure(error, context)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_bytes(encode(result))
    print(json.dumps({"status": result["status"], "record": result.get("record")}))


def feedback(client, number, result, *, receipt=None, commit=None):
    status = result["status"]
    context = result.get("context") or {}
    run_url = f"https://github.com/{CONFIG['repository']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    summary = {"format": "goo-ai-arena.feedback", "version": "0.1", "status": status,
               "record": receipt["record"] if receipt else result.get("record"),
               "checked_head_sha": context.get("head_sha"), "workflow_run": run_url,
               "publication_commit": commit, "issues": list(result.get("platform_issues", []))}
    if result.get("admission"):
        summary["issues"] += result["admission"]["errors"][:5]
        summary["warning_codes"] = sorted({i["code"] for i in result["admission"]["warnings"]})
    # Arbitrary submitted strings never become comment Markdown, mentions or shell commands.
    # Full location-rich errors are in the downloadable result.json artifact.
    summary["issues"] = [{"code": i["code"], "retryable": i.get("retryable", False)} for i in summary["issues"]]
    body = COMMENT_TAG + "\nFormal admission status; not a physics verdict.\n\n```json\n" + json.dumps(summary, indent=2) + "\n```\n\n"
    if receipt:
        record_id = receipt["record"]["id"]
        body += f"[Immutable receipt](https://github.com/{CONFIG['repository']}/blob/{CONFIG['branch']}/receipts/{record_id}.json). "
        body += "Data was imported as one atomic publication commit; the PR is closed, not merged.\n"
    else:
        body += "Download the admission-result artifact for full structured errors. Correct the same unpublished draft and push, or comment `/arena recheck` to retry. Code/rule changes need maintainer review.\n"
    comments = list(client.pages(f"/issues/{number}/comments"))
    matching = [item for item in comments if item["user"]["login"] == "github-actions[bot]" and item["body"].startswith(COMMENT_TAG)]
    if matching:
        client.request("PATCH", f"/issues/comments/{matching[-1]['id']}", {"body": body})
    else:
        client.request("POST", f"/issues/{number}/comments", {"body": body})
    if context.get("head_sha"):
        state = "success" if receipt else "failure" if status == "needs_correction" else "pending"
        client.request("POST", "/statuses/" + context["head_sha"], {
            "state": state, "context": "arena/formal-admission", "description": status,
            "target_url": run_url})


def publish(result_path, output_path):
    client = api()
    number = request_number()
    result = failure(RuntimeError())
    receipt = commit = None
    try:
        result = json.loads(result_path.read_text())
        context = result.get("context")
        if not context:
            raise PolicyError("CHECK_NOT_COMPLETED", "The checking job did not produce a bound result.", "pending")
        if (context["pr_number"] != number or context["repository"] != CONFIG["repository"]
                or context["branch"] != CONFIG["branch"] or context["trusted_sha"] != os.environ["GITHUB_SHA"]):
            raise PolicyError("UNBOUND_CHECK", "The result is not bound to this request, repository and trusted workflow revision.", "pending")
        pr = client.get(f"/pulls/{number}")
        if pr["head"]["sha"] != context["head_sha"]:
            raise PolicyError("STALE_HEAD", "The request changed after checking; recheck.", "pending")
        if result["status"] == "admitted":
            base_sha = client.get("/git/ref/heads/" + CONFIG["branch"])["object"]["sha"]
            base = client.tree(base_sha)
            receipts, records = registry(client, base)
            decision = publication_plan(result, pr, base_sha, base, receipts)
            if decision == "already_published":
                receipt = receipts[result["record"]["id"]]
                result["status"] = "already_published"
            else:
                comparison = client.get(f"/compare/{base_sha}...{context['head_sha']}")
                ancestor, head = client.tree(comparison["merge_base_commit"]["sha"]), client.tree(context["head_sha"])
                record_id, paths, manifest = data_delta(ancestor, head)
                if (record_id != result["record"]["id"] or manifest != context["manifest_path"]
                        or {path: head[path]["sha"] for path in paths} != context["blobs"]):
                    raise PolicyError("CHECKED_BYTES_CHANGED", "Publication input differs from the checked Git blobs.", "pending")
                from arena_contract.validator import parse_json, schema_validator
                schema_validator("Admission").validate(result["admission"])
                if result["admission"]["status"] != "admitted" or result["admission"]["record"] != result["record"]:
                    raise PolicyError("INCONSISTENT_ADMISSION", "The formal result does not admit this exact record.", "pending")
                raw = client.blob(head[manifest]["sha"])
                record = parse_json(raw)
                schema_validator("Record").validate(record)
                if digest(raw) != result["record"]["sha256"] or record["id"] != record_id:
                    raise PolicyError("MANIFEST_CHANGED", "The checked manifest identity does not match.", "pending")
                if record["purpose"] != ("demo" if CONFIG["demo_only"] else "competition"):
                    raise PolicyError("PURPOSE_NOT_ALLOWED", "The record purpose does not match this deployment's admission policy.")
                authorization(record, pr["user"], receipts)
                if not client.server_time:
                    raise PolicyError("SERVER_TIME_UNAVAILABLE", "GitHub did not provide a publication timestamp.", "pending")
                receipt = {"format": "goo-ai-arena.receipt", "version": "0.1", "stage": CONFIG["stage"],
                           "record": result["record"], "manifest_path": manifest,
                           "submitted_at": client.server_time, "request_opened_at": context["request_opened_at"],
                           "submission_time_basis": "GitHub API server time when this admission receipt was prepared; not creator-supplied build time.",
                           "submitted_by": context["submitted_by"], "pull_request": number,
                           "validated_head_sha": context["head_sha"], "validated_base_sha": context["base_sha"],
                           "platform_code_sha": context["trusted_sha"], "workflow_run_id": int(os.environ["GITHUB_RUN_ID"]),
                           "workflow_run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]), "admission": result["admission"]}
                from jsonschema import Draft202012Validator, FormatChecker
                Draft202012Validator(json.loads((HERE / "receipt.schema.json").read_text()), format_checker=FormatChecker()).validate(receipt)
                records[record_id], receipts[record_id] = record, receipt
                files = render_catalog(records, receipts)
                files[f"receipts/{record_id}.json"] = encode(receipt)
                # Reuse immutable Git blobs by SHA: the write job does not decode images or event streams.
                commit = client.commit_files(base_sha, files, f"Admit {record['purpose']} record {record_id} from PR #{number}", blobs=context["blobs"])
                latest_pr = client.get(f"/pulls/{number}")
                publication_plan(result, latest_pr, client.get("/git/ref/heads/" + CONFIG["branch"])["object"]["sha"], base, {})
                client.advance(CONFIG["branch"], commit)
                result["status"] = "published"
        feedback(client, number, result, receipt=receipt, commit=commit)
        if receipt:
            # Do not close a newer draft which appeared during publication.
            latest_pr = client.get(f"/pulls/{number}")
            if latest_pr["state"] == "open" and latest_pr["head"]["sha"] == result["context"]["head_sha"]:
                client.request("PATCH", f"/pulls/{number}", {"state": "closed"})
    except Exception as error:
        # If the main ref update succeeded but feedback failed, receipt lookup on retry recovers it.
        result = failure(error, result.get("context"))
        try:
            feedback(client, number, result)
        except Exception:
            pass
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encode(result))
    print(json.dumps({"status": result["status"], "record": result.get("record"), "publication_commit": commit}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "check", "publish"])
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.output)
    elif args.command == "check":
        check(args.input, args.output)
    else:
        publish(args.input, args.output)


if __name__ == "__main__":
    main()
