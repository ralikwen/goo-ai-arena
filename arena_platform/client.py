"""Explicit, recoverable GitHub submission client; no game or competitor code runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from urllib.parse import quote

from arena_contract.validator import MANIFESTS, parse_json, read_safe
from .core import UUID, PolicyError, digest
from .github import APIError, GitHub


def token_from_file(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Credential file must be an owner-only regular file")
        raw = stream.read(8193)
    token = raw.strip().decode("ascii")
    if not token or len(raw) > 8192 or any(character.isspace() for character in token):
        raise ValueError("Invalid credential file format")
    return token


def bundle_files(bundle):
    names = [name for name in MANIFESTS if (bundle / name).exists()]
    if len(names) != 1:
        raise ValueError("Exactly one manifest is required")
    raw = read_safe(bundle, names[0])
    record = parse_json(raw)
    if not isinstance(record, dict) or not re.fullmatch(UUID, record.get("id", "")):
        raise ValueError("A lowercase UUIDv4 record ID is required")
    declared = {names[0]} | {item["path"] for item in record["files"]}
    actual = {str(path.relative_to(bundle)) for path in bundle.rglob("*") if not path.is_dir() or path.is_symlink()}
    if actual != declared:
        raise ValueError("The bundle contains missing, undeclared or unsafe artifacts")
    files = {f"records/{record['id']}/{name}": read_safe(bundle, name) for name in sorted(declared)}
    return record, raw, files


def git_hash(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def lookup(client, record_id, branch="main"):
    if not re.fullmatch(UUID, record_id):
        raise ValueError("Invalid record UUID")
    tip = client.get("/git/ref/heads/" + branch)["object"]["sha"]
    tree = client.tree(tip)
    path = f"receipts/{record_id}.json"
    if path not in tree:
        return None, tree
    return json.loads(client.blob(tree[path]["sha"])), tree


def submit(client, bundle, *, head_client=None):
    record, raw, files = bundle_files(bundle)
    receipt, main_tree = lookup(client, record["id"])
    if receipt:
        expected = {path: git_hash(content) for path, content in files.items()}
        actual = {path: entry["sha"] for path, entry in main_tree.items()
                  if path.startswith(f"records/{record['id']}/")}
        if receipt["record"]["sha256"] != digest(raw) or expected != actual:
            raise PolicyError("IDENTITY_COLLISION", "This UUID is published with different bytes; use a linked new UUID.")
        return {"status": "already_published", "receipt": receipt}
    head_client = head_client or client
    branch = "arena/" + record["id"]
    try:
        parent = head_client.get("/git/ref/heads/" + branch)["object"]["sha"]
    except APIError as error:
        if error.status != 404:
            raise
        parent = client.get("/git/ref/heads/main")["object"]["sha"]
        head_client.request("POST", "/git/refs", {"ref": "refs/heads/" + branch, "sha": parent})
    current = head_client.tree(parent)
    changed = {path: content for path, content in files.items()
               if current.get(path, {}).get("sha") != git_hash(content)}
    removed = {path: None for path in current
               if path.startswith(f"records/{record['id']}/") and path not in files}
    if changed or removed:
        commit = head_client.commit_files(parent, changed, f"Submit record draft {record['id']}", blobs=removed)
        head_client.advance(branch, commit)
    head = head_client.repository.split("/")[0] + ":" + branch
    prs = client.get("/pulls?state=open&head=" + quote(head, safe="") + "&base=main&per_page=100")
    if prs:
        pr = prs[0]
    else:
        pr = client.request("POST", "/pulls", {
            "head": head, "base": "main", "title": f"[DATA] {record['id']}",
            "body": "Data-only record publication request. Submission attribution and evidence are in the bundle.\n\n"
                    f"Declared record purpose: {record['purpose']}. "
                    "Publish these contributed materials under the repository's stated licensing policy."})
    return {"status": "submitted", "record": {"id": record["id"], "sha256": digest(raw)},
            "pull_request": pr["number"], "url": pr["html_url"]}


def main():
    parser = argparse.ArgumentParser(description="Explicit GitHub data submission and recovery; never executes a builder")
    parser.add_argument("command", choices=["inspect", "submit", "lookup", "recheck"])
    parser.add_argument("value", help="Bundle directory, record UUID, or PR number")
    parser.add_argument("--repository", default=json.loads((Path(__file__).parent / "config.json").read_text())["repository"])
    parser.add_argument("--head-repository", help="Existing authorized fork for contributors without target-repository write access")
    parser.add_argument("--token-file", help="Owner-only credential file; otherwise read GH_TOKEN from the environment")
    parser.add_argument("--publish", action="store_true", help="Explicitly authorize this submission or recheck write")
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            record, raw, files = bundle_files(Path(args.value))
            result = {"status": "local_inspection_only", "record": {"id": record["id"], "sha256": digest(raw)}, "paths": sorted(files)}
        else:
            token = token_from_file(args.token_file) if args.token_file else os.environ["GH_TOKEN"]
            client = GitHub(args.repository, token)
            if args.command == "lookup":
                receipt, _ = lookup(client, args.value)
                result = {"status": "published" if receipt else "not_published", "receipt": receipt}
            elif not args.publish:
                raise ValueError("Writes require --publish; an entry URL alone is not publication authority")
            elif args.command == "submit":
                head_client = GitHub(args.head_repository, token) if args.head_repository else None
                result = submit(client, Path(args.value), head_client=head_client)
            else:
                if not re.fullmatch(r"[1-9][0-9]*", args.value):
                    raise ValueError("A positive pull request number is required")
                comment = client.request("POST", "/issues/" + args.value + "/comments", {"body": "/arena recheck"})
                result = {"status": "recheck_requested", "url": comment["html_url"]}
        print(json.dumps(result, indent=2))
    except (APIError, PolicyError, ValueError, OSError, KeyError):
        print(json.dumps({"status": "client_error", "message": "Check credentials, bundle, permissions and request parameters; no credential or server response body is disclosed."}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
