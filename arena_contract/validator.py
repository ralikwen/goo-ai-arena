"""Formal consistency checks on declarations. No native game or physics imports."""

from __future__ import annotations

import base64
import errno
import functools
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
from decimal import Decimal, DecimalException, localcontext
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

HERE = Path(__file__).parent
SCHEMA = json.loads((HERE / "schema.json").read_text(encoding="utf-8"))
MANIFESTS = {
    "submission.json": ("goo-ai-arena.submission", "Submission"),
    "report.json": ("goo-ai-arena.reproduction-report", "ReproductionReport"),
    "withdrawal.json": ("goo-ai-arena.withdrawal", "Withdrawal"),
}
CORE_CONTROLS = {"pointer_primary", "pointer_secondary", "whistle"}
PATH_RE = re.compile(r"[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*\Z")
EMPTY_INPUT = {"held_ball": None, "active_controls": []}


@functools.lru_cache(maxsize=None)
def schema_validator(name):
    return Draft202012Validator({"$schema": SCHEMA["$schema"], "$defs": SCHEMA["$defs"],
                                 "$ref": "#/$defs/" + name})


class DuplicateKey(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKey("Duplicate JSON object key")
        result[key] = value
    return result


def _noninteger(_):
    raise ValueError("Fractional quantities must be decimal strings; NaN/Infinity are forbidden")


def parse_json(raw):
    text = raw.decode("utf-8")
    if text.startswith("\ufeff"):
        raise ValueError("UTF-8 BOM is forbidden")
    return json.loads(text, object_pairs_hook=_pairs, parse_float=_noninteger,
                      parse_constant=_noninteger)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def pointer(parts):
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def safe_path(path):
    return (isinstance(path, str) and PATH_RE.fullmatch(path) is not None
            and all(p not in {".", ".."} for p in path.split("/")))


def read_safe(root, relative):
    """Open every component without following symlinks, including race replacements."""
    if not safe_path(relative):
        raise ValueError("Unsafe relative path")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = relative.split("/")
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        data_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(data_fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Only regular files are allowed")
            return stream.read()
    finally:
        os.close(fd)


def difference(end, start):
    # No implicit Decimal precision limit on recorded timestamps.
    with localcontext() as context:
        context.prec = len(end) + len(start) + 8
        return Decimal(end) - Decimal(start)


def input_equal(a, b):
    return a["held_ball"] == b["held_ball"] and set(a["active_controls"]) == set(b["active_controls"])


def is_input(event):
    return event["kind"] == "interaction" and event["operation"] != "pickup_end"


class BrowserDecoder:
    """Optional local adapter; deployment can provide another data-only decoder."""

    def __init__(self, timeout_s=20):
        self.cache = {}
        self.timeout_s = timeout_s  # An operational budget, not a competition rule.

    def __call__(self, raw, format_name):
        key = (sha256(raw), format_name)
        if key in self.cache:
            return self.cache[key]
        signatures = {"png": b"\x89PNG\r\n\x1a\n", "jpeg": b"\xff\xd8\xff"}
        if format_name not in signatures or not raw.startswith(signatures[format_name]):
            return "invalid", "Image signature does not match its declared format"
        environment = {k: os.environ[k] for k in ("PATH", "LANG", "NODE_PATH", "PLAYWRIGHT_BROWSERS_PATH") if k in os.environ}
        preferred = Path("/opt/peopletest-playwright/runner/node_modules")
        if "NODE_PATH" not in environment and preferred.is_dir():
            environment["NODE_PATH"] = str(preferred)
        browsers = Path("/opt/peopletest-playwright/browsers")
        if "PLAYWRIGHT_BROWSERS_PATH" not in environment and browsers.is_dir():
            environment["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)
        try:
            process = subprocess.Popen(
                ["node", str(HERE / "image_decoder.cjs")],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=environment, start_new_session=True,
            )
            try:
                stdout, _ = process.communicate(json.dumps({"bytes": base64.b64encode(raw).decode("ascii"),
                                                           "mediaType": "image/" + format_name,
                                                           "deadlineMs": max(1, int(self.timeout_s * 700))}), timeout=self.timeout_s)
            except subprocess.TimeoutExpired:
                # Let Playwright's termination handler close its browser first.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.communicate()
                raise
            decoded = json.loads(stdout)
            result = decoded["status"], decoded["message"]
            if result[0] not in {"ok", "invalid", "unavailable"}:
                raise ValueError("Unknown decoder result")
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError):
            result = "unavailable", "Image decoding could not finish; retry with an available decoder"
        if result[0] != "unavailable":
            self.cache[key] = result
        return result


class Checker:
    def __init__(self, *, allow_demo=False, rulesets=(), references=(), decoder=None):
        self.allow_demo = allow_demo
        self.rulesets = [HERE / "rulesets" / "corporation-state-300-v1.json", *map(Path, rulesets)]
        self.references = list(map(Path, references))
        self.decoder = decoder or BrowserDecoder()
        self.errors = []
        self.warnings = []
        self.record_ref = None
        self.manifest_name = None
        self.data = {}
        self.formats = {}
        self.unavailable_files = set()
        self.decoded_images = set()

    def issue(self, code, message, *, file=None, line=None, pointer=None,
              event_id=None, rule=None, retryable=False, warning=False):
        item = dict(code=code, file=file, line=line, pointer=pointer, event_id=event_id,
                    message=message, rule=rule, retryable=retryable)
        (self.warnings if warning else self.errors).append(item)

    def outcome(self):
        status = ("needs_correction" if any(not e["retryable"] for e in self.errors)
                  else "pending" if self.errors else "admitted")
        return dict(format="goo-ai-arena.admission", version="0.2", record=self.record_ref,
                    status=status, errors=self.errors, warnings=self.warnings)

    def document(self, raw, file, line=None):
        try:
            return parse_json(raw)
        except (ValueError, UnicodeError) as exc:
            self.issue("DUPLICATE_KEY" if isinstance(exc, DuplicateKey) else "JSON_INVALID",
                       str(exc), file=file, line=line)
            return None

    def schema(self, value, name, file, line=None):
        errors = list(schema_validator(name).iter_errors(value))
        for error in errors:
            unsafe = error.validator == "pattern" and error.schema.get("pattern") == SCHEMA["$defs"]["Path"]["pattern"]
            self.issue("UNSAFE_PATH" if unsafe else "SCHEMA_MISMATCH", error.message, file=file, line=line,
                       pointer=pointer(error.absolute_path),
                       event_id=value.get("id") if line and isinstance(value, dict) and isinstance(value.get("id"), str) else None)
        return not errors

    def bundle(self, root):
        root = Path(root).absolute()
        if root.is_symlink():
            self.issue("UNSAFE_PATH", "Bundle root must not be a symlink")
            return None
        if not root.is_dir():
            self.issue("INFRASTRUCTURE_UNAVAILABLE", "Bundle directory is unavailable", retryable=True)
            return None
        candidates = [n for n in MANIFESTS if (root / n).exists() or (root / n).is_symlink()]
        if len(candidates) != 1:
            self.issue("MISSING_MANIFEST", "Bundle must contain exactly one submission.json, report.json, or withdrawal.json")
            return None
        self.manifest_name = candidates[0]
        try:
            raw = read_safe(root, self.manifest_name)
        except (OSError, ValueError) as exc:
            unavailable = isinstance(exc, OSError) and exc.errno not in {errno.ELOOP, errno.ENOTDIR}
            self.issue("INFRASTRUCTURE_UNAVAILABLE" if unavailable else "UNSAFE_PATH",
                       "Manifest could not be read as a regular non-symlink file", file=self.manifest_name, retryable=unavailable)
            return None
        record = self.document(raw, self.manifest_name)
        if not isinstance(record, dict):
            self.issue("SCHEMA_MISMATCH", "Manifest must be a JSON object", file=self.manifest_name)
            return None
        if isinstance(record.get("version"), str) and record["version"] != "0.2":
            self.issue("UNSUPPORTED_VERSION", "This checker implements contract 0.2", file=self.manifest_name, retryable=True)
            return None
        if not self.schema(record, MANIFESTS[self.manifest_name][1], self.manifest_name):
            return None
        self.record_ref = {"id": record["id"], "sha256": sha256(raw)}
        if record["purpose"] == "demo":
            if not self.allow_demo:
                self.issue("DEMO_NOT_ALLOWED", "Synthetic fixtures are never competition submissions", file=self.manifest_name)
            self.issue("SYNTHETIC_FIXTURE", "Synthetic test data: no execution or reproduction is asserted", warning=True)
        declared = {self.manifest_name}
        for item in record["files"]:
            name = item["path"]
            if not safe_path(name):
                self.issue("UNSAFE_PATH", "Unsafe artifact path", file=name)
                continue
            if name in declared:
                self.issue("DUPLICATE_FILE", "Each artifact is listed once; the manifest must not hash itself", file=name)
                continue
            declared.add(name)
            self.formats[name] = item["format"]
            try:
                data = read_safe(root, name)
            except FileNotFoundError:
                self.issue("MISSING_FILE", "Declared artifact is missing", file=name)
                continue
            except (OSError, ValueError) as exc:
                unavailable = isinstance(exc, OSError) and exc.errno not in {errno.ELOOP, errno.ENOTDIR}
                if unavailable:
                    self.unavailable_files.add(name)
                self.issue("INFRASTRUCTURE_UNAVAILABLE" if unavailable else "UNSAFE_PATH",
                           "Artifact could not be read as a regular non-symlink file", file=name, retryable=unavailable)
                continue
            self.data[name] = data
            if sha256(data) != item["sha256"]:
                self.issue("HASH_MISMATCH", "Artifact bytes differ from the manifest hash", file=name)
            if item["format"] == "json":
                self.document(data, name)
            elif item["format"] == "jsonl":
                self.json_lines(data, name)
            elif item["format"] in {"png", "jpeg"}:
                self.decode_image(data, name, item["format"])
            elif item["format"] in {"text", "markdown"}:
                try:
                    if data.decode("utf-8").startswith("\ufeff"):
                        raise ValueError("BOM is forbidden")
                except (ValueError, UnicodeError):
                    self.issue("TEXT_INVALID", "Text must be UTF-8 without BOM", file=name)
        for directory, dirs, files in os.walk(root, followlinks=False):
            for name in dirs + files:
                path = Path(directory) / name
                relative = path.relative_to(root).as_posix()
                if not safe_path(relative) or path.is_symlink():
                    self.issue("UNSAFE_PATH", "Bundle contains an unsafe path or symlink", file=relative)
                elif path.is_file() and relative not in declared:
                    self.issue("UNDECLARED_FILE", "Artifact is not listed in the manifest", file=relative)
                elif not path.is_file() and not path.is_dir():
                    self.issue("UNSAFE_PATH", "Only regular files and directories are permitted", file=relative)
        self._check_urls(record)
        return record

    def _check_urls(self, value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "url" and isinstance(child, str):
                    try:
                        parsed = urlsplit(child)
                        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                            raise ValueError()
                    except ValueError:
                        self.issue("URL_INVALID", "Links must be HTTPS URLs without credentials", file=self.manifest_name)
                self._check_urls(child)
        elif isinstance(value, list):
            for child in value:
                self._check_urls(child)

    def load_ruleset(self, reference):
        same_id = False
        for path in self.rulesets:
            try:
                raw = path.read_bytes()
                profile = parse_json(raw)
            except (OSError, ValueError):
                continue
            if isinstance(profile, dict) and profile.get("id") == reference["id"]:
                same_id = True
                if sha256(raw) == reference["sha256"]:
                    if profile.get("version") != "0.1":
                        self.issue("UNSUPPORTED_VERSION", "Ruleset version is not supported by this checker", pointer="/ruleset", retryable=True)
                        return None
                    if self.schema(profile, "Ruleset", path.name):
                        return profile
                    return None
        self.issue("HASH_MISMATCH" if same_id else "UNKNOWN_RULESET",
                   "Supply the exact local ruleset bytes referenced by the record", file=self.manifest_name,
                   pointer="/ruleset", retryable=not same_id)
        return None

    def resolve(self, reference, field):
        same_id = False
        for source in self.references:
            paths = [source / n for n in MANIFESTS] if source.is_dir() else [source]
            for path in paths:
                if path.name not in MANIFESTS:
                    continue
                try:
                    raw = read_safe(path.parent, path.name)
                    value = parse_json(raw)
                except (OSError, ValueError):
                    continue
                if isinstance(value, dict) and value.get("id") == reference["id"]:
                    same_id = True
                    if sha256(raw) == reference["sha256"]:
                        if value.get("version") != "0.2":
                            self.issue("UNSUPPORTED_VERSION", "Referenced record version is not supported", pointer="/" + field, retryable=True)
                            return None
                        if self.schema(value, MANIFESTS[path.name][1], path.name):
                            if self.record_ref["id"] == reference["id"]:
                                self.issue("IDENTITY_CONFLICT", "Linked records must have distinct immutable IDs", pointer="/" + field)
                            return value
                        return None
        self.issue("HASH_MISMATCH" if same_id else "REFERENCE_UNAVAILABLE",
                   "Supply the exact target manifest as a local --reference", file=self.manifest_name,
                   pointer="/" + field, retryable=not same_id)
        return None

    def check_identity(self):
        for source in self.references:
            paths = [source / n for n in MANIFESTS] if source.is_dir() else [source]
            for path in paths:
                if path.name not in MANIFESTS:
                    continue
                try:
                    raw = read_safe(path.parent, path.name)
                    value = parse_json(raw)
                except (OSError, ValueError):
                    continue
                if isinstance(value, dict) and value.get("id") == self.record_ref["id"] and sha256(raw) != self.record_ref["sha256"]:
                    self.issue("IDENTITY_CONFLICT", "An existing immutable ID identifies different manifest bytes; create a new ID")

    def artifact(self, name, expected):
        if name not in self.data:
            if name not in self.unavailable_files:
                self.issue("MISSING_FILE", "Referenced artifact is not available", file=name)
            return None
        if self.formats.get(name) != expected:
            self.issue("FILE_FORMAT", "Artifact must be declared as " + expected, file=name)
            return None
        return self.data[name]

    def json_artifact(self, name, definition):
        raw = self.artifact(name, "json")
        if raw is None:
            return None
        value = self.document(raw, name)
        return value if self.schema(value, definition, name) else None

    def json_lines(self, raw, path):
        if not raw.endswith(b"\n") or b"\r" in raw:
            self.issue("JSONL_LAYOUT", "JSONL requires LF lines and a final LF, without CR", file=path)
        lines = raw.split(b"\n")
        if lines[-1] == b"":
            lines.pop()
        result = []
        for line, data in enumerate(lines, 1):
            value = self.document(data, path, line)
            if not isinstance(value, dict):
                self.issue("JSONL_LAYOUT", "Each JSONL line must be an object", file=path, line=line)
            else:
                result.append((line, value))
        return result

    def events(self, paths):
        events = []
        locations = {}
        for path in paths:
            raw = self.artifact(path, "jsonl")
            if raw is None:
                continue
            for line, value in self.json_lines(raw, path):
                kind = value.get("kind") if isinstance(value, dict) else None
                definition = {"interaction": "Interaction", "state": "State", "marker": "Marker"}.get(kind, "Event")
                if not self.schema(value, definition, path, line):
                    continue
                if value["id"] in locations:
                    self.issue("DUPLICATE_ID", "Event IDs must be unique across all chunks", file=path, line=line, event_id=value["id"])
                locations[value["id"]] = (path, line)
                events.append(value)
        return events, locations

    def image(self, descriptor, purpose):
        if descriptor is None:
            return
        name = descriptor["path"]
        if purpose == "competition" and descriptor["origin"] != "game_screenshot":
            self.issue("IMAGE_REQUIREMENT", "Competition evidence must be a finished native game screenshot", file=name)
        if purpose == "demo" and (descriptor["origin"] != "demo_image" or not descriptor["caption"].startswith("[DEMO] ")):
            self.issue("DEMO_LABEL", "Synthetic image evidence must have demo_image origin and a [DEMO] caption", file=name)
        format_name = self.formats.get(name)
        if format_name not in {"png", "jpeg"}:
            self.issue("IMAGE_REQUIREMENT", "Screenshot must be a declared PNG or JPEG", file=name)
            return
        raw = self.artifact(name, format_name)
        if raw is not None:
            self.decode_image(raw, name, format_name)

    def native_save(self, descriptor, purpose):
        if descriptor is None:
            return  # Only unsuccessful reports may omit the save; schema checks this.
        name = descriptor["path"]
        raw = self.artifact(name, "native_save")
        if purpose == "competition" and descriptor["origin"] != "game_save":
            self.issue("SAVE_ORIGIN", "Competition evidence must be a game-written native save", file=name)
        if purpose == "demo" and (descriptor["origin"] != "demo_save" or not descriptor["notes"].startswith("[DEMO] ")):
            self.issue("DEMO_LABEL", "Synthetic saves require demo_save origin and [DEMO] notes", file=name)
        if raw is not None:
            if not raw:
                self.issue("SAVE_EMPTY", "Native save artifact must not be empty", file=name)
            else:
                self.issue("NATIVE_SAVE_UNVERIFIED", "Save bytes and declarations are recorded; native format, restorability, tower correspondence and legal construction are not verified", file=name, warning=True)

    def decode_image(self, raw, name, format_name):
        if name in self.decoded_images:
            return
        self.decoded_images.add(name)
        status, message = self.decoder(raw, format_name)
        if status != "ok" and not any(i["file"] == name and i["code"] in {"IMAGE_INVALID", "INFRASTRUCTURE_UNAVAILABLE"} for i in self.errors):
            self.issue("IMAGE_INVALID" if status == "invalid" else "INFRASTRUCTURE_UNAVAILABLE",
                       message, file=name, retryable=status != "invalid")

    def validate(self, root):
        try:
            record = self.bundle(root)
            if record is None or any(not e["retryable"] for e in self.errors):
                return self.outcome()
            kind = record["format"]
            self.check_identity()
            for field in ("revises", "target"):
                if record.get(field) is not None:
                    resolved = self.resolve(record[field], field)
                    if resolved:
                        if record["purpose"] != resolved["purpose"]:
                            self.issue("PURPOSE_MISMATCH", "Competition and demo records cannot cross-reference", pointer="/" + field)
                        if field == "revises" and resolved["format"] != kind:
                            self.issue("REFERENCE_TYPE", "A revision must revise the same record type", pointer="/revises")
                        if field == "target" and kind == "goo-ai-arena.reproduction-report":
                            if resolved["format"] != "goo-ai-arena.submission":
                                self.issue("REFERENCE_TYPE", "A reproduction report must target a submission", pointer="/target")
                            elif record["ruleset"] != resolved["ruleset"] and record["verdict"] == "reproduced":
                                self.issue("RULE_VIOLATION", "Successful reproduction must satisfy the target ruleset", pointer="/ruleset")
                    if field == "target":
                        target = resolved
            if kind == "goo-ai-arena.withdrawal":
                self.issue("ATTRIBUTION_UNVERIFIED", "Local checking cannot authorize a withdrawal or authenticate its author", warning=True)
                return self.outcome()
            profile = self.load_ruleset(record["ruleset"])
            success = kind == "goo-ai-arena.submission" or record["verdict"] == "reproduced"
            execution = record["execution"]
            measurement = None
            if execution is not None:
                measurement = self.execution(execution, record, profile, success)
            if success and measurement is not None:
                claim = record["claim"] if kind == "goo-ai-arena.submission" else (target or {}).get("claim")
                if claim is not None and Decimal(measurement) < Decimal(claim["height_m"]):
                    self.issue("HEIGHT_CLAIM", "Recorded native measurement is below the claimed height", file=self.manifest_name)
            if record["external_evidence"]:
                self.issue("EXTERNAL_EVIDENCE_UNCHECKED", "External evidence is linked but never fetched or executed", warning=True)
            self.issue("DECLARATIONS_NOT_PROVEN", "Formal admission does not prove execution, measured clocks, legal physics, authorship, or reproducibility", warning=True)
        except (MemoryError, RecursionError, DecimalException, OSError):
            self.issue("INFRASTRUCTURE_UNAVAILABLE", "Validation could not finish with available resources", retryable=True)
        return self.outcome()

    def execution(self, execution, record, profile, success):
        self.issue("PROCESS_CLAIM_UNVERIFIED", "Discovery and construction involvement is self-declared; human oversight, autonomy and provenance are not independently verified", pointer="/execution/process_claim", warning=True)
        start = self.json_artifact(execution["start_file"], "Start")
        final = self.json_artifact(execution["final_file"], "Final") if execution["final_file"] else None
        events, locations = self.events(execution["event_files"])
        self.image(execution["image"], record["purpose"])
        self.native_save(execution["native_save"], record["purpose"])
        if start is None or not events or any(e["code"] in {"SCHEMA_MISMATCH", "JSON_INVALID", "DUPLICATE_KEY", "DUPLICATE_ID"} for e in self.errors):
            if not events and not (set(execution["event_files"]) & self.unavailable_files):
                self.issue("EMPTY_TRACE", "An execution must contain recorded events")
            return None
        def problem(code, message, event=None, **kwargs):
            if event is not None:
                path, line = locations[event["id"]]
                kwargs.update(file=path, line=line, event_id=event["id"])
            self.issue(code, message, **kwargs)
        def rule(message):
            problem("RULE_VIOLATION" if success else "EVIDENCE_RULE_DEVIATION", message,
                    warning=not success, rule=profile["id"] if profile else None)
        balls = {}
        for ball in start["balls"]:
            if ball["id"] in balls:
                problem("DUPLICATE_ID", "Starting ball IDs must be unique")
            balls[ball["id"]] = dict(ball)
        if profile:
            if len(start["balls"]) != profile["material_count"]:
                rule("Starting material does not match the ruleset allowance")
            if start["start_class"] not in profile["start_classes"]:
                rule("The declared starting class is not permitted by the ruleset")
            env = execution["environment"]
            if not profile["allow_gameplay_modifications"] and env["gameplay_modifications"]:
                rule("The execution declares gameplay modifications forbidden by the ruleset")
            if not profile["allow_state_injection"] and env["state_injection_during_construction"]:
                rule("The execution declares forbidden state injection")
        connections = {}
        used_connections = set()
        def add_connection(connection, event=None):
            cid = connection["id"]
            if cid in used_connections:
                problem("DUPLICATE_ID", "Connection IDs cannot be reused", event)
            used_connections.add(cid)
            connections[cid] = dict(connection)
        def check_graph(event=None):
            for connection in connections.values():
                a, b = connection["a"], connection["b"]
                if a == b or a not in balls or b not in balls:
                    problem("UNDEFINED_REFERENCE", "Connection endpoints must be distinct existing balls", event)
                elif balls[a]["role"] != "construction" or balls[b]["role"] != "construction":
                    problem("MATERIAL_ACCOUNTING", "Live connections require construction-role endpoints", event)
        for connection in start["connections"]:
            add_connection(connection)
        check_graph()
        if profile and profile.get("initial_triangle_required"):
            attached = {b["id"] for b in start["balls"] if b["role"] == "construction"}
            edges = {frozenset((c["a"], c["b"])) for c in start["connections"]}
            if len(attached) != 3 or len(start["connections"]) != 3 or len(edges) != 3:
                rule("The starting construction must be the supplied three-ball triangle, not a prebuilt tower")
        custom = {}
        controls = set(CORE_CONTROLS)
        for definition in execution["custom_operations"]:
            if definition["id"] in custom:
                problem("DUPLICATE_ID", "Custom operation definitions must be unique")
            names = [p["name"] for p in definition["parameters"]]
            if len(names) != len(set(names)):
                problem("DUPLICATE_ID", "Custom parameter definitions must be unique")
            custom[definition["id"]] = definition
        for definition in execution["custom_controls"]:
            if not definition["id"].startswith("x:") or definition["id"] in controls:
                problem("DUPLICATE_ID", "Custom controls must have unique namespaced IDs")
            controls.add(definition["id"])
        seen = {}
        phases = {}
        previous_time = {"wall_s": "0", "game_s": "0"}
        previous_input = dict(EMPTY_INPUT)
        resolved_pickups = set()
        reported_custom = set()
        for index, event in enumerate(events):
            for clock in ("wall_s", "game_s"):
                if Decimal(event["at"][clock]) < Decimal(previous_time[clock]):
                    problem("TIMELINE_INCONSISTENT", "Both clocks must be nondecreasing in file order", event)
            previous_time = event["at"]
            current_input = event.get("input_state")
            if current_input is not None:
                holder = current_input["held_ball"]
                if holder is not None and (holder not in balls or balls[holder]["role"] in {"consumed", "discarded"}):
                    problem("UNDEFINED_REFERENCE", "Held ball must be available in the declared state", event)
                if not set(current_input["active_controls"]) <= controls:
                    problem("UNDEFINED_REFERENCE", "Input snapshot uses an undefined control", event)
            if event["kind"] == "interaction":
                for name in event["objects"]["balls"]:
                    if name not in balls or balls[name]["role"] in {"consumed", "discarded"}:
                        problem("UNDEFINED_REFERENCE", "Interaction refers to an unavailable ball", event)
                for name in event["objects"]["connections"]:
                    if name not in connections:
                        problem("UNDEFINED_REFERENCE", "Interaction refers to an unavailable connection", event)
                self.interaction(event, previous_input, seen, resolved_pickups, custom,
                                 controls, balls, connections, problem, reported_custom)
            elif event["kind"] == "state":
                cause = event["cause"]
                if cause is not None and (cause not in seen or seen[cause]["kind"] != "interaction"):
                    problem("UNDEFINED_REFERENCE", "State cause must identify an earlier interaction or be null", event)
                changes = event["changes"]
                for name in changes["connections_removed"]:
                    if name not in connections:
                        problem("UNDEFINED_REFERENCE", "Cannot remove an absent connection", event)
                    connections.pop(name, None)
                for key, id_key in (("ball_roles", "ball"), ("ball_properties", "ball"), ("connection_properties", "connection")):
                    ids = [c[id_key] for c in changes[key]]
                    if len(ids) != len(set(ids)):
                        problem("DUPLICATE_ID", "A state change field may update an object only once", event)
                for change in changes["ball_roles"]:
                    name = change["ball"]
                    if name not in balls:
                        problem("UNDEFINED_REFERENCE", "State changes cannot create new material", event)
                    elif balls[name]["role"] != change["from"]:
                        problem("MATERIAL_ACCOUNTING", "Role transition contradicts the preceding declared state", event)
                    elif change["from"] in {"consumed", "discarded"} and change["to"] != change["from"]:
                        problem("MATERIAL_ACCOUNTING", "Consumed or permanently discarded material cannot reappear", event)
                    else:
                        balls[name]["role"] = change["to"]
                for change in changes["ball_properties"]:
                    if change["ball"] not in balls:
                        problem("UNDEFINED_REFERENCE", "Unknown ball in property update", event)
                    else:
                        balls[change["ball"]]["properties"] = change["properties"]
                for connection in changes["connections_added"]:
                    add_connection(connection, event)
                for change in changes["connection_properties"]:
                    if change["connection"] not in connections:
                        problem("UNDEFINED_REFERENCE", "Unknown connection in property update", event)
                    else:
                        connections[change["connection"]]["properties"] = change["properties"]
                positions = [p["ball"] for p in event["positions"]]
                if len(positions) != len(set(positions)):
                    problem("DUPLICATE_ID", "Duplicate position observation", event)
                for name in positions:
                    if name not in balls or balls[name]["role"] == "consumed":
                        problem("UNDEFINED_REFERENCE", "Position observation refers to absent material", event)
                check_graph(event)
                if current_input is not None and current_input["held_ball"] is not None:
                    holder = current_input["held_ball"]
                    if holder in balls and balls[holder]["role"] in {"consumed", "discarded"}:
                        problem("INPUT_CONTRADICTION", "Post-transition input state cannot hold consumed or discarded material", event)
            else:
                phase = event["phase"]
                if phase in phases:
                    problem("TIMELINE_INCONSISTENT", "Each execution phase occurs at most once; do not splice attempts", event)
                phases[phase] = index
                if phase != "measured" and (event["height_m"] is not None or event["height_resolution_m"] is not None):
                    problem("HEIGHT_CLAIM", "Native measurement fields belong to the measured marker", event)
            if current_input is not None:
                previous_input = current_input
            seen[event["id"]] = event
        if phases.get("construction_started") != 0 or any(Decimal(v) != 0 for v in events[0]["at"].values()):
            problem("TIMELINE_INCONSISTENT", "First event must mark construction start at zero on both clocks")
        inputs = [e for e in events if is_input(e)]
        if inputs and any(Decimal(v) != 0 for v in inputs[0]["at"].values()):
            problem("TIMELINE_INCONSISTENT", "Clock origin is the first construction input")
        if success and not inputs:
            problem("UNBUILT", "A completed submission needs an executed construction history")
        if final is not None:
            final_balls = {b["id"]: b for b in final["balls"]}
            if len(final_balls) != len(final["balls"]) or set(final_balls) != set(balls):
                problem("MATERIAL_ACCOUNTING", "Final state must account for every starting ball exactly once")
            for name, ball in final_balls.items():
                if name in balls and (ball["role"] != balls[name]["role"] or ball["properties"] != balls[name]["properties"]):
                    problem("FINAL_STATE_MISMATCH", "Final roles and properties contradict the declared transitions")
                if ball["role"] == "consumed" and ball["position"] is not None:
                    problem("MATERIAL_ACCOUNTING", "Consumed material has no final position")
            final_connections = {c["id"]: c for c in final["connections"]}
            if len(final_connections) != len(final["connections"]) or final_connections != connections:
                problem("FINAL_STATE_MISMATCH", "Final connections contradict the declared transitions")
            if profile and profile["require_all_material_used"] and any(b["role"] not in {"construction", "consumed"} for b in final["balls"]):
                rule("All supplied material must be used in construction; unused inventory and discarding do not qualify")
        measurement = self.timelines(execution, events, phases, profile, success, problem, rule)
        for quiet in execution["quiet_periods"]:
            if quiet["held_ball"] is not None and quiet["held_ball"] not in balls:
                problem("UNDEFINED_REFERENCE", "Quiet interval names an unknown ball")
            if not set(quiet["active_controls"]) <= controls:
                problem("UNDEFINED_REFERENCE", "Quiet interval names an undefined control")
        guide = record.get("reproduction_guide")
        if guide:
            for note in guide["notes"]:
                if any(name not in seen for name in note["event_ids"]):
                    problem("UNDEFINED_REFERENCE", "Reproduction guidance links an unknown event", pointer="/reproduction_guide")
        return measurement

    def interaction(self, event, previous_input, seen, resolved_pickups, custom,
                    controls, balls, connections, problem, reported_custom):
        operation = event["operation"]
        objects = event["objects"]
        params = event["parameters"]
        state = event["input_state"]
        count = len(objects["balls"]), len(objects["connections"])
        if operation.startswith("x:"):
            if operation not in custom:
                problem("UNDEFINED_OPERATION", "Custom operations require a published definition", event)
                return
            definitions = {p["name"]: p for p in custom[operation]["parameters"]}
            if set(params) - set(definitions) or any(p["required"] and p["name"] not in params for p in definitions.values()):
                problem("SCHEMA_MISMATCH", "Custom parameters do not match their declaration", event)
            for name, value in params.items():
                if name not in definitions:
                    continue
                kind = definitions[name]["type"]
                if kind in {"ball_id", "connection_id"}:
                    available = balls if kind == "ball_id" else connections
                    if not isinstance(value, str) or value not in available:
                        problem("UNDEFINED_REFERENCE", "Custom parameter names an unavailable object", event)
                else:
                    definition = {"decimal": "Decimal", "point": "Point", "json": "Json", "string": "Text"}.get(kind)
                    if definition:
                        valid = schema_validator(definition).is_valid(value)
                    else:
                        valid = isinstance(value, bool)
                    if not valid:
                        problem("SCHEMA_MISMATCH", "Custom parameter has the wrong declared type", event)
            if operation not in reported_custom:
                problem("CUSTOM_OPERATION_NOT_MODELED", "Definition recorded; physics and method are not modeled: " + operation, event, warning=True)
                reported_custom.add(operation)
            return
        expected = {"pickup_begin": {(1, 0)}, "pickup_end": {(1, 0)}, "detach": {(1, 0), (0, 1)},
                    "camera": {(0, 0)}, "control": {(0, 0)}, "move": {(0, 0), (1, 0)}}
        if operation in expected and count not in expected[operation]:
            problem("OBJECT_COUNT", "Core operation has the wrong object references", event)
        if operation == "release":
            if count[0] != 1 or (count[0] == 1 and previous_input["held_ball"] != objects["balls"][0]) or state["held_ball"] is not None:
                problem("INPUT_CONTRADICTION", "Release must identify the previously held ball and end with no held ball", event)
        elif operation == "pickup_end":
            begin = params["begin"]
            prior = seen.get(begin)
            if (prior is None or prior.get("operation") != "pickup_begin" or prior.get("objects") != objects or begin in resolved_pickups):
                problem("UNDEFINED_REFERENCE", "Pickup observation needs one unresolved earlier pickup_begin of the same target", event)
            resolved_pickups.add(begin)
            target = objects["balls"][0] if count[0] == 1 else None
            holder = state["held_ball"]
            if ((params["result"] == "held" and holder != target)
                    or (params["result"] == "not_held" and holder is not None)
                    or (params["result"] == "other_ball" and (holder is None or holder == target))):
                problem("INPUT_CONTRADICTION", "Pickup result contradicts the held-ball observation", event)
        elif operation == "move" and count[0] == 1 and objects["balls"][0] != previous_input["held_ball"]:
            problem("INPUT_CONTRADICTION", "Move object must be the held ball", event)
        elif operation == "control":
            control = params["control"]
            if control not in controls or ((control in state["active_controls"]) != params["pressed"]):
                problem("INPUT_CONTRADICTION", "Control event contradicts its input snapshot or definition", event)

    def timelines(self, execution, events, phases, profile, success, problem, rule):
        timing = execution["timing"]
        complete = execution["completeness"] == "complete"
        start = phases.get("construction_started")
        hands = phases.get("hands_off_started")
        measured = phases.get("measured")
        if complete and (start != 0 or hands is None or measured != len(events) - 1 or not (0 < hands < measured)):
            problem("TIMELINE_INCONSISTENT", "Complete trace requires ordered start, hands-off, and final measured markers")
        if measured is not None and (hands is None or hands >= measured):
            problem("TIMELINE_INCONSISTENT", "Measurement must follow hands-off start")
        if measured is not None and measured != len(events) - 1:
            problem("TIMELINE_INCONSISTENT", "Measurement must end this attempt")
        if not complete and measured is not None:
            problem("TIMELINE_INCONSISTENT", "A partial trace ends at its real stopping point without a completed measurement marker")
        for key in ("wall_s", "game_s"):
            if Decimal(timing["total"][key]) != Decimal(events[-1]["at"][key]):
                problem("TIMELINE_INCONSISTENT", "Total duration must end at the last recorded event")
            if hands is not None:
                if timing["construction"] is None or Decimal(timing["construction"][key]) != Decimal(events[hands]["at"][key]):
                    problem("TIMELINE_INCONSISTENT", "Construction duration must end at hands-off start")
            elif timing["construction"] is not None:
                problem("TIMELINE_INCONSISTENT", "An unfinished construction has no completed construction duration")
            if measured is not None and hands is not None:
                if timing["hold"] is None or Decimal(timing["hold"][key]) != difference(events[measured]["at"][key], events[hands]["at"][key]):
                    problem("TIMELINE_INCONSISTENT", "Hold duration must match its actual event boundaries")
            elif timing["hold"] is not None:
                problem("TIMELINE_INCONSISTENT", "An unfinished hold has no completed hold duration")
        indices = {e["id"]: i for i, e in enumerate(events)}
        normal_intervals = []
        intervals = []
        for quiet in execution["quiet_periods"]:
            a, b = indices.get(quiet["from"]), indices.get(quiet["to"])
            if a is None or b is None or a >= b:
                problem("UNDEFINED_REFERENCE", "Quiet interval must reference ordered event endpoints")
                continue
            expected = {k: quiet[k] for k in ("held_ball", "active_controls")}
            for other_a, other_b, other in intervals:
                if max(a, other_a) < min(b, other_b) and (quiet["gameplay"] != other["gameplay"] or not input_equal(quiet, other)):
                    problem("QUIET_CONTRADICTION", "Overlapping quiet declarations disagree about gameplay or held inputs")
            intervals.append((a, b, quiet))
            for i in range(a, b + 1):
                event = events[i]
                if a < i < b and is_input(event):
                    problem("QUIET_CONTRADICTION", "Quiet interval contains an input action", event)
                snapshot = event.get("input_state")
                if snapshot is not None and not (i == b and is_input(event)) and not input_equal(expected, snapshot):
                    problem("QUIET_CONTRADICTION", "Quiet interval contradicts a held-ball/control observation", event)
            if quiet["gameplay"] == "paused":
                if difference(events[b]["at"]["game_s"], events[a]["at"]["game_s"]) != 0:
                    problem("QUIET_CONTRADICTION", "Paused interval cannot advance game time")
            elif input_equal(expected, EMPTY_INPUT):
                normal_intervals.append((a, b))
        if hands is not None and measured is not None:
            if any(is_input(e) or (e.get("input_state") is not None and not input_equal(e["input_state"], EMPTY_INPUT)) for e in events[hands:measured + 1]):
                rule("Final hands-off period contains input, a held ball, or an active control")
            covered = hands
            for a, b in sorted(normal_intervals):
                if a <= covered < b:
                    covered = b
            if covered < measured:
                rule("Explicit normal-gameplay quiet intervals must cover the final hold")
            if profile and difference(events[measured]["at"]["game_s"], events[hands]["at"]["game_s"]) < Decimal(profile["hold_game_s"]):
                rule("Final hold is shorter than the ruleset's required game time")
        if measured is not None:
            event = events[measured]
            if event["height_m"] is None or event["height_resolution_m"] is None:
                problem("HEIGHT_CLAIM", "Measurement needs the observed native height and resolution", event)
                return None
            return event["height_m"]
        return None


def validate_bundle(root, **kwargs):
    """One immutable record per invocation; the result is not a publication receipt."""
    return Checker(**kwargs).validate(root)
