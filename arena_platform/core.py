"""Pure publication policy and escaped, read-only presentation. No credentials."""

from __future__ import annotations

import hashlib
import html
import json
import re
from decimal import Decimal
from pathlib import Path

UUID = r"[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}"
FILE = re.compile(r"records/(?P<id>" + UUID + r")/(?P<path>[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*)\Z")
MANIFEST_NAMES = {"submission.json", "report.json", "withdrawal.json"}
PROCESS_LABELS = {
    "machine_only": "Fully machine discovery and building",
    "human_and_machine": "Human and machine — including human oversight",
    "human_only": "Fully human discovery and building",
}


class PolicyError(ValueError):
    def __init__(self, code, message, status="needs_correction"):
        self.code, self.status = code, status
        super().__init__(message)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def data_delta(ancestor, head):
    """Inspect a complete tree delta, not GitHub's capped PR files list."""
    paths = sorted(path for path in set(ancestor) | set(head)
                   if ancestor.get(path) != head.get(path))
    if not paths:
        raise PolicyError("NO_RECORD_CHANGE", "No new record bundle was found.")
    ids = set()
    for path in paths:
        match = FILE.fullmatch(path)
        if not match or any(part in {".", ".."} for part in path.split("/")):
            raise PolicyError("MAINTAINER_REVIEW", "This request changes protected repository content, such as platform code or rules. An authorized maintainer must review it before it can proceed. This is unrelated to the tower's height or ranking.", "maintainer_review")
        if path in ancestor:
            raise PolicyError("IMMUTABLE_RECORD", "Published records cannot be edited or deleted; add a linked new record.")
        entry = head[path]
        if entry.get("type") != "blob" or entry.get("mode") != "100644":
            raise PolicyError("UNSAFE_GIT_ENTRY", "Record data must be regular, non-executable Git blobs; no symlinks or submodules.")
        ids.add(match["id"])
    if len(ids) != 1:
        raise PolicyError("ONE_RECORD_PER_REQUEST", "Use one record bundle per pull request.")
    record_id = next(iter(ids))
    manifests = [path for path in paths if path == f"records/{record_id}/" + path.split("/")[-1]
                 and path.split("/")[-1] in MANIFEST_NAMES]
    if len(manifests) != 1:
        raise PolicyError("MANIFEST_COUNT", "The bundle needs exactly one top-level submission, report or withdrawal manifest.")
    return record_id, paths, manifests[0]


def authorization(record, author, receipts):
    """The original authenticated uploader controls revisions/withdrawal, not names."""
    references = []
    if record.get("revises"):
        references.append(record["revises"])
    if record.get("format") == "goo-ai-arena.withdrawal":
        references.append(record["target"])
    for reference in references:
        receipt = receipts.get(reference["id"])
        if not receipt:
            raise PolicyError("REFERENCE_UNAVAILABLE", "The referenced record has no publication receipt.", "pending")
        if receipt["record"] != reference:
            raise PolicyError("REFERENCE_HASH_MISMATCH", "The reference does not match the published manifest hash.")
        if receipt["submitted_by"]["id"] != author["id"]:
            raise PolicyError("NOT_RECORD_UPLOADER", "Only the original authenticated uploader can automatically revise or withdraw a record.")


def publication_plan(result, pr, current_base, current_files, receipts):
    """Rebind a read-only check to live GitHub state before any publication write."""
    if result.get("status") != "admitted":
        raise PolicyError("NOT_ADMITTED", "Only an admitted result can be published.", "pending")
    context = result["context"]
    if pr["number"] != context["pr_number"] or pr["user"]["id"] != context["submitted_by"]["id"]:
        raise PolicyError("IDENTITY_CHANGED", "The request or submitting account changed.", "pending")
    if pr["head"]["sha"] != context["head_sha"]:
        raise PolicyError("STALE_HEAD", "The pull request changed after validation; recheck its current revision.", "pending")
    record_id = result["record"]["id"]
    existing = receipts.get(record_id)
    if existing:
        if existing["record"] != result["record"]:
            raise PolicyError("IDENTITY_COLLISION", "This record ID is already published with different manifest bytes.")
        expected = context["blobs"]
        actual = {path: entry["sha"] for path, entry in current_files.items()
                  if path.startswith(f"records/{record_id}/")}
        if actual != expected:
            raise PolicyError("PUBLISHED_BYTES_CHANGED", "Existing bundle bytes do not match the checked request.", "pending")
        return "already_published"
    if pr["state"] != "open" or pr.get("draft"):
        raise PolicyError("REQUEST_NOT_OPEN", "The pull request must still be open and ready for publication.", "pending")
    if pr["base"]["ref"] != context["branch"]:
        raise PolicyError("WRONG_BASE", "The request no longer targets the configured publication branch.", "pending")
    if current_base != context["base_sha"]:
        raise PolicyError("STALE_BASE", "The registry changed after validation; recheck against its current state.", "pending")
    if any(path.startswith(f"records/{record_id}/") for path in current_files):
        raise PolicyError("RECEIPT_MISSING", "A bundle exists without its atomic publication receipt; maintainer investigation is needed.", "pending")
    return "publish"


def text(value):
    # Text is used in Markdown text/labels, never HTML attributes. Quoting an
    # apostrophe creates a numeric entity whose '#' the next step would escape.
    value = html.escape(str(value), quote=False).replace("\r", " ").replace("\n", " ")
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~])", r"\\\1", value)


def render_catalog(records, receipts):
    """Build JSON index and Markdown pages; never render submitted HTML or fetch URLs."""
    entries = []
    files = {}
    successors = {rid: [] for rid in records}
    for rid, record in records.items():
        previous = record.get("revises")
        if (previous and previous["id"] in records
                and previous == receipts[previous["id"]]["record"]
                and record["format"] == records[previous["id"]]["format"]
                and record["purpose"] == records[previous["id"]]["purpose"]):
            successors[previous["id"]].append(rid)

    def latest_revisions(rid):
        pending, visited, latest = list(successors[rid]), {rid}, set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            if successors[current]:
                pending.extend(successors[current])
            else:
                latest.add(current)
        return sorted(latest)

    for record_id, record in sorted(records.items()):
        receipt = receipts[record_id]
        kind = record["format"].split(".")[-1]
        execution = record.get("execution")
        reports = [{"record": receipts[rid]["record"], "verdict": item["verdict"],
                    "reporter": item["reporter"], "submitted_by": receipts[rid]["submitted_by"],
                    "withdrawn": any(other["format"] == "goo-ai-arena.withdrawal" and other["target"] == receipts[rid]["record"] for other in records.values())}
                   for rid, item in sorted(records.items())
                   if item["format"] == "goo-ai-arena.reproduction-report"
                   and item["target"] == receipt["record"]]
        withdrawals = [receipts[rid]["record"] for rid, item in records.items()
                       if item["format"] == "goo-ai-arena.withdrawal" and item["target"] == receipt["record"]]
        entry = {"record": receipt["record"], "kind": kind,
                 "title": record.get("title", "Withdrawal"), "purpose": record["purpose"],
                 "manifest": receipt["manifest_path"], "page": f"catalog/{record_id}.md",
                 "receipt": f"receipts/{record_id}.json", "submitted_at": receipt["submitted_at"],
                 "submitted_by": receipt["submitted_by"], "formal_status": "admitted",
                 "height_m": record.get("claim", {}).get("height_m"),
                 "contract_version": record["version"],
                 "native_save": execution.get("native_save") if execution else None,
                 "process_claim": execution.get("process_claim") if execution else None,
                 "timing": execution["timing"] if execution else None,
                 "creators": record.get("creators"), "about": record.get("about"),
                 "verdict": record.get("verdict"), "target": record.get("target"),
                 "revises": record.get("revises"), "reports": reports, "withdrawals": withdrawals,
                 "superseded_by": [receipts[rid]["record"] for rid in sorted(successors[record_id])],
                 "latest_revisions": [receipts[rid]["record"] for rid in latest_revisions(record_id)]}
        entries.append(entry)
        lines = [f"# {text(entry['title'])}", "", "SYNTHETIC DEMO — not a competition entry." if record["purpose"] == "demo" else "Competition entry.", "",
                 "Formal checks: admitted. This is not proof of execution, legality or reproducibility.", "",
                 f"Authenticated submitting account: {text(receipt['submitted_by']['login'])} (GitHub ID {receipt['submitted_by']['id']}).", "",
                 f"Platform submission time: {text(receipt['submitted_at'])}.", "",
                 f"[Exact bundle manifest](../{receipt['manifest_path']}) · [Publication receipt](../receipts/{record_id}.json)", ""]
        if successors[record_id]:
            latest_links = ", ".join(f"[Latest revision]({rid}.md)" for rid in latest_revisions(record_id))
            lines.extend([f"Historical version — superseded. {latest_links}. Earlier files and reports remain available.", ""])
        readable = [item for item in record.get("files", [])
                    if item["format"] == "markdown" and FILE.fullmatch(f"records/{record_id}/{item['path']}")]
        if readable:
            labels = {"readme.md": "Entry overview", "rebuild.md": "Rebuilding guide",
                      "rebuild-steps.md": "Placement sequence", "setup.md": "Starting setup"}
            lines.extend(["## Build instructions", ""])
            for item in readable:
                path = item["path"]
                lines.append(f"- [{text(labels.get(path, path))}](../records/{record_id}/{path})")
            lines.append("")
        if entry["height_m"] is not None:
            lines.extend([f"Claimed native height: {text(entry['height_m'])} m.", "",
                          "Creators (submitted attribution): " + ", ".join(text(c["name"]) for c in record["creators"]) + ".", ""])
        if execution:
            process_claim = execution.get("process_claim")
            lines.extend(["## Discovery and building (self-declared)", ""])
            if process_claim:
                lines.extend([text(PROCESS_LABELS[process_claim["mode"]]) + ".", "",
                              text(process_claim["description"]), "",
                              "This is the submitter's claim, not independently verified by the platform. It does not change admission or height ranking.", ""])
            else:
                lines.extend(["Not declared in this historical entry; do not infer human or machine involvement from the creator's identity or tools.", ""])
            lines.extend(["## Recorded duration", "", "| Phase | Wall seconds | Game seconds |", "| --- | --- | --- |"])
            for phase in ("construction", "hold", "total"):
                duration = execution["timing"][phase]
                lines.append(f"| {phase} | {text(duration['wall_s']) if duration else 'Not completed'} | {text(duration['game_s']) if duration else 'Not completed'} |")
            lines.append("")
            if execution["image"]:
                image_label = "Synthetic demo image" if record["purpose"] == "demo" else "Finished tower screenshot"
                lines.extend([f"![{image_label}](../records/{record_id}/{execution['image']['path']})", ""])
                lines.extend([text(execution["image"]["caption"]), ""])
            save = execution.get("native_save")
            if save:
                save_hash = next(item["sha256"] for item in record["files"] if item["path"] == save["path"])
                lines.extend(["## Saved tower artifact", "",
                    f"[Download save artifact](../records/{record_id}/{save['path']}) — origin: {text(save['origin'])}.", "",
                    f"SHA-256: {save_hash}.", "",
                    f"Game version: {text(execution['environment']['version'])}; platform: {text(execution['environment']['platform'])}.", "",
                    f"Profile: {text(save['profile'])}.", "",
                    f"Restoration instructions (untrusted submitted data): {text(save['restore_instructions'])}", "",
                    f"Capture and limitations: {text(save['notes'])}", "",
                    "Presence is not proof of native validity, restorability, tower correspondence or legal construction."
                    + (" Demo placeholders are not restorable." if record["purpose"] == "demo" else ""), ""])
            elif record["version"] == "0.1":
                lines.extend(["Historical contract 0.1 record: no mandatory native-save check was performed.", ""])
        if record.get("about"):
            about = record["about"]
            lines.extend(["## Note and tooling", ""])
            for field in ("background", "method", "hardware", "preparation"):
                if about.get(field):
                    label = "Note" if field == "background" else field.capitalize()
                    lines.extend([f"{label}: {text(about[field])}", ""])
            for tool in about.get("tools", []):
                lines.extend([f"Tool: {text(tool['name'])}; version: {text(tool.get('version') or 'unspecified')}; role: {text(tool['role'])}.", ""])
            for credit in about.get("credits", []):
                lines.extend([f"Credit: {text(credit['name'])} — {text(credit['contribution'])}.", ""])
        if record.get("verdict"):
            lines.extend([f"Reporter's verdict: **{record['verdict']}** — {text(record['reporter']['name'])}.", "",
                          f"[Exact target record](../catalog/{record['target']['id']}.md), manifest SHA-256: {record['target']['sha256']}.", ""])
            for field in ("relation_to_creator", "method", "differences", "shared_dependencies", "evidence_limitations"):
                lines.extend([f"{field.replace('_', ' ').capitalize()}: {text(record[field])}", ""])
        if record["format"] == "goo-ai-arena.withdrawal":
            lines.extend([f"Withdrawal reason: {text(record['reason'])}", ""])
        if record.get("revises"):
            lines.extend([f"Revises [{record['revises']['id']}]({record['revises']['id']}.md); earlier evidence is retained.", ""])
        lines.extend(["## Attributed reproduction reports", ""])
        if not reports:
            lines.extend(["No reproduction verdicts reported for this exact manifest.", ""])
        for report in reports:
            label = report['verdict'] + (" (withdrawn)" if report['withdrawn'] else "")
            lines.extend([f"- [{label}]({report['record']['id']}.md) — {text(report['reporter']['name'])}; submitted by {text(report['submitted_by']['login'])}.", ""])
        for withdrawal in withdrawals:
            lines.extend([f"Withdrawn by an [attributed withdrawal]({withdrawal['id']}.md). Original evidence remains available.", ""])
        files[f"catalog/{record_id}.md"] = "\n".join(lines).encode("utf-8")
    towers = sorted((e for e in entries if e["kind"] == "submission"),
                    key=lambda e: (-Decimal(e["height_m"]), e["submitted_at"], e["record"]["id"]))
    competition_towers = [e for e in towers if e["purpose"] == "competition" and not e["withdrawals"] and not e["superseded_by"]]
    overview = ["# Tower catalogue", "", "Competition entries are ranked below. Historical synthetic demos remain in the machine-readable index and do not count as competition entries.", "",
                "Height determines ranking, not admission. Qualifying towers need not beat an earlier height or introduce a new design.", "",
                "Only current revisions are ranked. Superseded versions remain available through each entry's history and the index.", "",
                "Height is the submitter's claim. Admission checks declarations; reproduction verdicts belong to their reporters.", "",
                "| Tower claim | Height (m) | Discovery / building (self-declared) | Construction wall / game (s) | Platform submission time | Reports |", "| --- | --- | --- | --- | --- | --- |"]
    for entry in competition_towers:
        duration = entry["timing"]["construction"]
        label = text(entry["title"]) + (" (withdrawn)" if entry["withdrawals"] else "")
        process = PROCESS_LABELS[entry["process_claim"]["mode"]] if entry["process_claim"] else "Not declared"
        overview.append(f"| [{label}]({entry['record']['id']}.md) | {text(entry['height_m'])} | {text(process)} | {text(duration['wall_s'])} / {text(duration['game_s'])} | {text(entry['submitted_at'])} | {len(entry['reports'])} attributed |")
    if not competition_towers:
        overview.extend(["", "No competition submissions published yet."])
    overview.extend(["", "All reports, corrections and withdrawals remain in the [machine-readable index](index.json).", ""])
    files["catalog/README.md"] = "\n".join(overview).encode("utf-8")
    files["catalog/index.json"] = encode({"format": "goo-ai-arena.catalog", "version": "0.1",
                                           "stage": json.loads((Path(__file__).parent / "config.json").read_text())["stage"], "official_record_count": len(competition_towers), "records": entries})
    return files
