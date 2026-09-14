# Goo AI Arena — local submission contract v0.2

Start here. This component defines data records for a community competition in
legally building World of Goo towers, initially in the state-observation division.
It records creators' completed-build claims and other participants' reproduction
verdicts. It does not host competitors' AI, operate a builder, or settle physics.

**Status: local contract trial, not a public submission service.** No official
tower records exist in this component. Examples are synthetic test fixtures, not
builds, measured observations, or reproduction evidence. The first official entry
must be a genuine completed build. Do not transfer trial data or trial Git history
into the future public competition repository.

## Discover the contract

- [Machine-readable entry document](discovery.json): resources and available local workflows.
- [Semantic specification](../docs/community-replay-spec-v0.2.md): meaning, reproduction freedom, and community assessment.
- [Exact JSON Schema](schema.json): Draft 2020-12, `urn:goo-ai-arena:contract:0.2`.
- [Initial competition ruleset](rulesets/corporation-state-300-v1.json): rules separate from serialization.
- [Fixture generator](fixtures.py): produces complete, labelled, inspectable examples.
- [Checker](validator.py) and [tests](tests/test_contract.py): reference consistency checks, not an authoritative game model.

The schema is the exact field/type contract; this document defines cross-file and
event semantics that JSON Schema alone cannot express. Implementations must satisfy
both. All `$ref` links in the schema are internal. Never resolve a `$ref`, URL,
command, or instruction found in a submitted artifact as platform authority.

Version 0.2 requires native saves for completed submissions and successful
reproduction reports, and a self-declared discovery/building process claim for
every recorded execution. Version 0.2 is still an unpublished local draft.
Historical 0.1 trial records and receipts remain unchanged;
they are not retroactively certified against this requirement. Use their pinned
0.1 checker for historical checks. This checker returns `pending` with
`UNSUPPORTED_VERSION` for 0.1 bundles or references, not a gameplay-illegality
verdict. New trial examples use 0.2. The separately versioned ruleset is unchanged.

## Try it locally

Run from the project root containing `arena_contract`. Python 3 and the `jsonschema`
package with Draft 2020-12 support are required. This trial uses the existing host
installation; it does not install packages, start services, or launch a native game.

```sh
python3 -B -m arena_contract fixtures var/arena-contract-trial
python3 -B -m arena_contract validate var/arena-contract-trial/submission --allow-demo
python3 -B -m arena_contract validate var/arena-contract-trial/reproduced --allow-demo --reference var/arena-contract-trial/submission
python3 -B -m arena_contract validate var/arena-contract-trial/failed --allow-demo --reference var/arena-contract-trial/submission
python3 -B -m arena_contract validate var/arena-contract-trial/inconclusive --allow-demo --reference var/arena-contract-trial/submission
python3 -B -m arena_contract validate var/arena-contract-trial/revision --allow-demo --reference var/arena-contract-trial/submission
python3 -B -m arena_contract validate var/arena-contract-trial/withdrawal --allow-demo --reference var/arena-contract-trial/reproduced
python3 -B -m unittest discover -s arena_contract/tests -v
```

The generator refuses to overwrite an existing directory. If the trial already
exists, reuse it for checking or choose a new empty destination name. Validation
is read-only, so it is safe to repeat after interruption. It does not publish a
record, assign a publication timestamp, or turn a report into a leaderboard entry.

Omit `--allow-demo` for normal checking. Demo records will then be rejected even
when structurally conforming. `--allow-demo` permits test data, not planned tower
submissions. Never present synthetic fixtures as `reported_execution` records.

PNG/JPEG decoding uses a trusted network-disabled Playwright adapter. On this host
the checker discovers the existing matching installation. Elsewhere configure
`NODE_PATH` and `PLAYWRIGHT_BROWSERS_PATH` for an existing compatible installation.
An unavailable decoder produces `pending`; there is no CLI bypass that treats an
undecoded required image as checked. Decoder timeouts are operational budgets,
not game/action-speed rules. Deployments must select their own trusted, suitably
isolated decoder; the submitter cannot choose executable validation logic.

## Exact package layout and primitives

One bundle directory contains exactly one of `submission.json`, `report.json`, or
`withdrawal.json`. The manifest identifies every other file in `files`, each with
`path`, `format`, and lowercase SHA-256. It does not hash itself. The SHA-256 of
the exact manifest bytes identifies this version and commits to its listed hashes.
There is no JSON canonicalization; reformatting changes the version hash.

An execution normally uses `start.json`, `final.json`, `events/0001.jsonl`, and
`finished.png`, plus a native save such as `save/pers3.dat` for a successful build;
their actual relative paths are declared in `execution` and may
differ. `event_files` defines chunk order. All referenced artifacts must also
appear in `files`. No undeclared files, self-hashing manifests, duplicate file
entries, symlinks, special files, absolute paths, or path traversal are permitted.

JSON and text use UTF-8 without BOM. JSON has no duplicate keys, comments, NaN, or
Infinity. JSONL has one JSON object per LF-terminated line, no blank lines or CR,
and a final LF. Core fractional quantities are decimal strings, not JSON floating
point numbers or exponent notation. General metadata permits safe integers,
strings, booleans, nulls, arrays and objects; represent fractions as strings.

IDs are lowercase UUIDv4 for records and persistent locally assigned names for
balls, connections, and events. They need not be native pointers or recorder IDs.
Custom operation/control IDs use `x:` names. Field requirements and permitted
nulls are exact in the schema; only `about`, `reproduction_guide`, and execution
`coordinates` may be omitted from their respective objects. Core objects reject
unknown fields; namespaced `extensions` carries optional metadata, never new rules.

Select the appropriate `$defs` entry from `schema.json`:

| Data | Definition | Meaning |
| --- | --- | --- |
| `submission.json` | `Submission` | Creator's completed, actually executed build claim |
| `report.json` | `ReproductionReport` | One reporter's actual attempt and explicit verdict |
| `withdrawal.json` | `Withdrawal` | Attributed request to withdraw an existing record, retaining it |
| Starting artifact | `Start` | Starting resources, identity policy, declared state and start class |
| Final artifact | `Final` | Final material roles, properties, positions and connections |
| Native-save descriptor | `NativeSave` | Required game-written finished-tower save for successful builds; opaque bytes in a declared file |
| Process attribution | `ProcessClaim` | Required self-declared human/machine roles in each recorded discovery/building process |
| Each event line | `Event` | Concrete input, observed state change, or phase boundary |
| Ruleset document | `Ruleset` | Versioned competition constraints |
| Checker stdout | `Admission` | Formal checking outcome, not a publication receipt |

## Submission and execution

A competition submission has `format: "goo-ai-arena.submission"`, `version: "0.2"`,
`purpose: "competition"`, and `claim_kind: "reported_execution"`. It includes
`id`, `revises` (null or exact previous record reference), `title`, `creators`,
`ruleset`, `claim`, `execution`, `files`, `external_evidence`, and `extensions`.
`claim` specifies native `height_m`, a description of the intended tower, and
the measurement method. A screenshot is required, with `origin: "game_screenshot"`.
Demo submissions instead require `claim_kind: "synthetic_fixture"`, a `[DEMO]`
title, a `demo_image` with a `[DEMO]` caption, and a `demo_save` with `[DEMO]` notes.
Image authenticity is not proved
by a manifest field, hash, signature, or successful decoding.

`execution` contains `completeness`, `environment`, `process_claim`, optional `coordinates`,
`start_file`, `final_file`, `event_files`, `timing`, `quiet_periods`, `image`, `native_save`,
`custom_operations`, and `custom_controls`. Completed submissions require complete
traces, final state, screenshot, and native finished-tower save. Environment describes the game version,
platform, executable and physics-asset hashes, settings, gameplay modifications,
and any state injection. These are attributed declarations, not local inspections
of the submitter's software. Do not include the game binaries or proprietary assets.

### Required discovery and building claim

Every non-null execution includes `process_claim`, independent of optional
background/tooling disclosures and of whether its trace is complete or partial:

```json
{
  "mode": "human_and_machine",
  "description": "The AI proposed designs and placed balls. A human supervised the attempts, selected candidates and supplied design feedback."
}
```

Both fields are required; `description` must contain non-whitespace text explaining
the actual human and machine roles. `mode` is exactly one of:

- `machine_only`: fully machine-driven tower discovery and construction, without
  tower-specific human design guidance, candidate selection, supervision, approvals
  or interventions during that process.
- `human_and_machine`: any combination of human and machine contributions,
  including human oversight even without direct game input. This also covers a
  human-designed tower built by automation, or machine design advice used by a
  human builder. Describe the split instead of labelling these machine-only.
- `human_only`: humans discovered/designed the tower and performed its construction,
  without machine-generated design advice, search or automated building. Ordinary
  game controls, recording and measurement tools do not alone make a build mixed.

The scope is this tower's discovery and construction, not the historical creation
of every game, model or tool. Routine installation, stating the general objective,
starting an otherwise autonomous run and authorizing publication do not alone
count as human oversight. Tower-specific prompts, plans, selection or corrections
do count. Explain inherited tower-specific designs or dependencies in the claim;
do not infer machine-only discovery from automated placement alone.

The platform publishes this as self-declared attribution and emits
`PROCESS_CLAIM_UNVERIFIED`. It does not infer or authenticate the mode from creator
identity, tools, screenshots, logs, saves or GitHub accounts. All three modes are
eligible under the same rules; this creates no additional division, ranking bonus
or height gate. Detailed model/tool/background disclosure remains optional.

A reproduction report describes its own process, not the original creator's.
Reusing the target design is a disclosed dependency, not a claim of independently
inventing that design. An inconclusive report with `execution: null` has no process
claim to fabricate. Historical entries without the field display "Not declared";
do not backfill a mode. Changing a published claim requires a linked revision.

### Required native save

Every submission and `reproduced` report must attach its own actual game-written
save containing that attempt's finished tower. This is the game's native format,
not a new interchange format, an image, a graph export, or a reconstruction created
from the logs. The exact file name is not prescribed: different game versions may
use different names or encodings. List the file in `files` with
`format: "native_save"` and the SHA-256 of its unchanged raw bytes. A remote link
in `external_evidence` does not replace this required in-bundle attachment.

`execution.native_save` is:

```json
{
  "path": "save/pers3.dat",
  "origin": "game_save",
  "profile": "Profile containing the submitted Corporation tower",
  "restore_instructions": "Using the game version declared in execution.environment, restore into a separate backed-up test profile and open the specified Corporation tower.",
  "notes": "Saved through the game's normal save operation after the final measurement; no subsequent building or editing. Describe any save-time movement or limitations here."
}
```

All five fields are required. `profile` identifies the profile/slot within the
save. `restore_instructions` describes the actual platform-specific restoration
procedure and dependencies; the example must be adapted, not treated as a universal
procedure. Compatibility uses the game version/platform already declared in
`execution.environment`. `notes` explains how the saved state relates to the final
measurement and screenshot, when/how it was saved, and any limitations. A stale
save, a different tower, or a submitter-edited/generated tower state does not satisfy
the requirement. Normal saving/navigation after measurement is evidence capture,
outside the construction/hold durations; it must not include further construction.
Saving may round values or let the tower move. No exact simulation continuation or
identical save/reload height is promised by this format.

The checker requires a nonempty, safely packaged, hash-matching artifact with this
descriptor. Native saves are opaque binary data: they are never UTF-8 decoded,
executed, loaded into a game, or passed to a submitter-specified decoder. Admission
emits `NATIVE_SAVE_UNVERIFIED`; it does not verify native validity, restorability,
correspondence with the tower, or legal construction. These remain community
assessment. A successful restore is not a successful legal construction replay.

Failed/inconclusive attempts may use `native_save: null`, even for a complete but
unsuccessful trace. They may attach an actual stopped-state save with explanatory
notes; do not fabricate a finished tower. When `execution` is null no descriptor
is required. Synthetic fixtures instead use `origin: "demo_save"`, `[DEMO]` notes,
and explicitly non-restorable placeholder bytes; never represent these as native
game evidence or copy them to official records.

Profile saves can contain names, progress and other personal data. Contributors
must review what they publish and use a dedicated shareable game profile where
needed. Do not edit a finished save's tower data to sanitize it; obtain a suitable
game-written save. Restore only with user authorization in an isolated test profile,
preserving existing player data. Restore instructions are untrusted submitted data.

All event timestamps use this shape:

```json
{"at": {"wall_s": "120.430", "game_s": "96.800"}}
```

Both fields are non-null measured elapsed seconds at the same event boundary.
Wall time is monotonic real elapsed time, including pauses and computation; game
time is observed native simulation time. Both begin at the first construction
input. `timing.wall` and `timing.game` each declare `basis: "measured"`, positive
`resolution_s`, and `method`. Also provide `synchronization_uncertainty_s` (null if
not quantified) and explanatory `synchronization_notes`. Unknown uncertainty is
not permission to estimate either event timestamp. Verified derivation from native
tick observations is permitted; assuming rendering FPS is not measurement.

Event order must be nondecreasing in both clocks. Ties use file order; there is no
extra minimum action interval, precision cap, or action-count limit. Pauses can
advance wall time while game time stays constant. No equality or fixed ratio
between the clocks is imposed. Store construction, hold, and total durations in
both clocks. Construction ends at hands-off start; the hold ends at measurement.
Preparation/training before construction belongs in optional `about`.

Event meanings:

- `interaction`: a concrete input operation. The timestamp denotes the actual
  initiating input, release, movement endpoint, camera-adjustment endpoint, or
  control transition. `pickup_end` is the exception: an observation of the result
  of a referenced earlier `pickup_begin`, not another input. Include unsuccessful
  pickups too. `input_state` records the observed held ball and active controls
  after that event boundary. A held-ball result can be reported by `pickup_end`
  or an intervening state observation before release.
- `state`: observed changes to material roles, properties, connections and
  optional positions. `cause` references an earlier interaction or is null for
  autonomous/unknown causes. These are declarations, never state-injection commands.
  Property updates replace the object's entire declared non-positional properties.
- `marker`: `construction_started`, `hands_off_started`, or `measured`. A complete
  trace starts at the first marker at zero on both clocks and ends at `measured`.
  Only `measured` carries non-null native height and height resolution.

Core operation object/parameter shapes are constrained by `Interaction` and checked
across events. `release.position` is the released ball's target, `move.position`
the cursor/held movement target, and `camera.center` the submitted camera center.
No coordinate conversion or physical geometry test is performed. Recommend native
world coordinates where available. Explain deviations if useful; uninterpretable
coordinates alone are not an admission failure.

Define non-core inputs in `custom_operations` with their meaning, timestamp
boundary, and named typed parameters. Custom controls require their own definitions.
Defined unsupported operations are admitted with a warning unless the declarations
explicitly contradict a rule. Their physical effects are not simulated or inferred
from the current recorder. Their claimed effects belong in subsequent state events.

`quiet_periods` explicitly records event-bounded intervals without new input,
including any held ball/control and `gameplay: "normal"` or `"paused"`. The span
starts after its `from` event and ends before any new input at its `to` event.
State observations and `pickup_end` are not additional inputs, but must agree with
the declared held state. Missing actions alone are not explicit quiet evidence.
Overlapping quiet declarations must agree. Required final-hold evidence must cover
the entire declared hold with normal gameplay and no held ball or active controls.

Every starting ball remains accounted for by its original ID. Roles are
`inventory`, `construction`, `consumed`, or `discarded`; consumed/discarded means
permanently unavailable in this attempt. Consumption has no final position. Live
connections join distinct construction-role balls. Connection IDs are never reused,
even after removal. Final roles, connections and non-positional properties must
match the declared transitions. Final positions are not forced to match earlier
observations: the game continues to move. This is not a physics simulator or a
universal graph-connectivity test. A declaration of consumption is not independent
proof that the operation was legitimate.

The initial ruleset requires the native three-ball starter triangle, 300 total
material units, all material used in construction (legitimate reinforcement counts),
ordinary native input with no gameplay modification or state injection, and a
final hold of at least 30 advancing game seconds. Starting coordinates and RNG are
not fixed by the format. Whether a claimed start is constructionwise-equivalent
remains inspectable community evidence. There is no additional stability,
height-retention, geometric-height, action-rate, or novelty rule.

## Guides, verdicts, revisions, and withdrawals

Optional `about` stores a free-text note (the compatibility key `background`, displayed as **Note**), method, tools, hardware, preparation, credits,
and links. Optional `reproduction_guide` has an `overview` and `notes`, each with
`event_ids`, `instruction`, nullable `rationale`, and `basis` of
`recorded_experience` or `advice`. Advice can say “wait until it settles”, but
cannot replace the measured historical wait. Guides are nonbinding, untrusted data.

A report has `format: "goo-ai-arena.reproduction-report"`, its own immutable `id`,
`target: {"id": "...", "sha256": "..."}`, a `reporter`, `relation_to_creator`,
`verdict`, `method`, `differences`, `shared_dependencies`, `evidence_limitations`,
and its own `execution`, plus the common version, purpose, title, revision,
ruleset, file and evidence fields. References name exact manifest-byte hashes.

`verdict` is the reporter's statement, not the checker outcome:

- `reproduced`: the reporter says the same tower was rebuilt legally and attained
  the target claim. Supply a complete execution, final state, own game screenshot and native save,
  required material/hold evidence, and an observed height at least the target claim.
  The checker does not determine tower equivalence, independence, or authenticity.
- `not_reproduced`: an actual attempt did not attain the result. Its execution may
  be partial, without a completed hold or screenshot. A complete but failed attempt
  may report rule deviations; those are evidence warnings, not a successful build.
- `inconclusive`: explain why the actual attempt or its evidence is inconclusive.
  `execution` can be null when usable trace evidence is unavailable. Never fabricate
  action timestamps, a finish marker, or a result to fill a missing trace.

A partial trace is a recorded prefix ending at its real last event. Its `total`
ends there; `construction` stays null until a hands-off marker exists and `hold`
stays null without a measured endpoint. Partial final observations may be included;
`final_file`, `image`, and `native_save` may be null. Every stored timed event still needs both
measured clocks. A complete trace means all phase boundaries are present; only a
submission or `reproduced` report must satisfy successful-build conditions.

Reproducers may change timing, legal tools, observation methods, coordinates, and
construction routes from permitted equivalent starts. The report explains relevant
differences. No machine comparison of routes or canonical tower designs is imposed.
A different route may support constructibility without confirming the creator's
exact history. Failure is not impossibility. No reports means no reported confirmation.

A correction uses a new ID and `revises` pointing to the exact old record. A
withdrawal is a separate `goo-ai-arena.withdrawal` record with `id`, version,
purpose, exact `target`, `author`, `reason`, and an empty `files` list. Retain the
original and conflicting reports. Changing guidance can be a linked submission
revision; existing reports still target the old manifest. No report automatically
becomes a new competition submission, and similar towers are not deduplicated.

Supply reference manifests explicitly with repeatable `--reference` inputs and
additional profiles with repeatable `--ruleset` inputs. The initial profile ships
locally. Missing referenced data produces `pending`; a supplied matching ID with
the wrong hash produces `needs_correction`. Identity collisions are checked against
the supplied local references, not an imaginary global registry. Resolution checks
target-manifest schema and identity, not re-admission of the target package; run the
target's own full validation separately. No external links are fetched automatically.

The local checker cannot authenticate attribution or authorize corrections or
withdrawals on someone else's behalf. Those are trusted publication-workflow
responsibilities. A local admission also does not confirm previous publication.

## Interpret results and recover

`Admission` contains `record`, `status`, `errors`, and `warnings`. Each issue has
`code`, `file`, one-based JSONL `line`, JSON `pointer`, `event_id`, `message`, `rule`,
and `retryable`; unavailable locations are null. `record` is null when a valid
record identity could not be read. Results are JSON; process exit codes are:

| Exit | Status | Next action |
| --- | --- | --- |
| 0 | `admitted` | Formal checks passed; inspect warnings. This is not publication or validation of physics. |
| 1 | `needs_correction` | Correct the cited data; already published content needs a new linked record. |
| 2 | `pending` | Supply missing references/runtime or retry after an operational failure. |

Definite errors take precedence over pending checks. Typical errors include
`SCHEMA_MISMATCH`, `UNSAFE_PATH`, `HASH_MISMATCH`, `UNDEFINED_REFERENCE`,
`TIMELINE_INCONSISTENT`, `MATERIAL_ACCOUNTING`, `FINAL_STATE_MISMATCH`, and
`RULE_VIOLATION`. `CUSTOM_OPERATION_NOT_MODELED` is a warning, not a rejection.
`UNKNOWN_RULESET`, `REFERENCE_UNAVAILABLE`, `UNSUPPORTED_VERSION`, and
`INFRASTRUCTURE_UNAVAILABLE` are pending when the missing capability/data prevents
completion. Preserve the reporter's verdict regardless of this separate outcome.

There is no network publication operation or credential requirement in this local checker.
Receiving an entry URL is not authorization to publish under a person's identity.
The [GitHub submission platform](../arena_platform/README.md) adds
authenticated submission accounts, immutable publication receipts, platform
timestamps, isolated checking/publication jobs, exact checked-revision binding,
recoverable retries, and read-only Markdown/JSON presentation. Its examples are
synthetic only. Public outside-fork testing and unauthenticated URL-only onboarding
remain later milestones; a public entry URL must be sufficient for discovery.
