# World of Goo construction submissions — semantic specification v0.2

Draft for community review · 2026-09-14

## 1. Purpose and admission

A submission is a precise, time-indexed record of a construction the creator
reports actually executing, and a claim about the resulting tower. Unexecuted
proposals and planned actions are not submissions. Publication does not require a
working player, the author's software, or a successful independent reproduction.

The submitted sequence describes what the creator claims happened, including how
long they actually waited. It is not an adaptive
building policy. Reproduction asks whether the same tower can be built legally;
it does not require matching the creator's timing or input trace.

The standard defines meaning and evidence independently of any recorder, player,
or operating system. The local [v0.2 contract](../arena_contract/README.md) supplies
the JSON/JSONL serialization, schemas, examples, and reference formal checker.

Admission checks descriptive completeness, valid references and well-defined
events and timings, plus a small set of formal checks on the submitted data:

- Declared material use must not exceed the ruleset's allowance, including
  material consumed during construction, not just balls remaining in the tower.
- All balls supplied for the attempt must be used in construction, with none
  left unused at completion. Legitimate consumption by reinforcement or another
  permitted construction operation counts as use.
- Declared operations and materials must not explicitly violate the rules.
  Other impossibilities established directly from the submitted data and rules
  are grounds for exclusion; uncertain physical feasibility is not.

A failed formal check excludes the submission from eligible competition entries
and must identify the violated rule and offending data or step. Passing these
checks does not establish that the claimed execution occurred or that the complete
construction is physically feasible or reproducible. A missing player or an
unsuccessful reproduction attempt is not, by itself, a formal contradiction.

An unsupported operation with a complete published definition is admissible; an
operation whose meaning is missing requires clarification. Rejected or later
disqualified sequences may be retained as historical or diagnostic records, with
their exclusion and contrary evidence visible, not as eligible competitive claims.

By default, a claim of height H means that at least one legal construction of the
specified tower can reach a native height of at least H at the prescribed
measurement point. Reports retain the actual native value and precision.
Reliability across repeated attempts
or different starts is a separate claim requiring corresponding evidence.

## 2. What a sequence means

Every submission must identify:

| Element | Required meaning |
| --- | --- |
| Identity | Creator attribution, specification version, submission version, and any parent submission. |
| Rules | The competition ruleset and game environment being claimed, including game and physics-asset hashes, versions and relevant settings. |
| Start | An initial state or initialization procedure, resources, object identities, and any conditions on randomness. An allowed class of equivalent starts must have explicit boundaries. |
| Sequence | An ordered account of actually executed actions and observed construction events, plus the final measurement procedure. |
| Timeline | Measured elapsed wall time and game time for every timed event, with a common origin, event boundaries, precision, acquisition method, and synchronization uncertainty. |
| Structure | The resulting tower's balls and connection graph, stated explicitly or derivable unambiguously from the sequence. Distinguish tower balls from loose inventory and consumed material. |
| Claim | Claimed native height in metres and the structural properties that identify the intended construction. |
| Discovery/building involvement | Self-declared machine-only, human-and-machine (including oversight), or human-only process, with an explanation of the actual roles. |

Every recorded execution declares whether its tower-specific discovery and
construction were entirely machine-driven, involved both humans and machines
(including human supervision), or were entirely human. The required explanation
covers design guidance, candidate selection, oversight and interventions, not just
who issued game inputs. Human-designed plans executed by automation are mixed.
Ordinary recording/measurement tools do not alone make human building mixed;
routine setup and publication authorization do not alone make autonomous building
human-supervised. Prior creation of general-purpose software/models is outside
this claim's scope, but inherited tower-specific designs must be explained.

This is an attributed claim, not a platform-verified conclusion. It does not
change admission or ranking, and detailed tooling/background disclosure remains
optional. Reproduction attempts declare their own involvement and disclose use of
the target design without claiming its independent invention. No claim is invented
for a report without a usable execution trace or for historical missing metadata.

Every starting ball must be accounted for as part of the completed construction
or as material legitimately consumed by a permitted construction operation.
For a 300-ball start, all 300 must be used; leaving balls unused or merely
discarding them does not satisfy this requirement. Consumed material is recorded
separately from balls remaining in the tower. This is a material-use requirement,
not a graph-connectivity test. The creator must report an actual completed build;
an independently working replayer is not required.

Each step must describe a concrete operation, such as adding a ball, removing a
joint or reinforcing a connection. It identifies the affected objects, geometric
target where applicable, any stated geometric tolerance,
and the reported change to the structure. Object references must remain
interpretable across implementations, including after creation, detachment or consumption.
Interchangeable objects require an explicit selection rule or permission to choose
among them. Placement targets refer to the placement event; any required later
shape must be identified separately.

These operations describe construction through ordinary game input.
They do not authorize direct creation of balls, connections or coordinates in the
game state. A report of execution can be admitted even when no current reproducer
can repeat it. This is different from submitting an unexecuted proposal.

Using the game's native world-coordinate system is recommended where available.
When another convention is used, explaining its origin, units, axes, camera
dependencies, or conversion is recommended to help reproduction. Coordinate
explanations are optional; no common frame, calibration action, mandatory
conversion, or platform judgment of decipherability is imposed.

Timing is required evidence about the submitted execution, not a schedule imposed
on the reproducer. Every recorded timed event supplies both `wall_s` and `game_s`
as non-null measured decimal strings. Both clocks begin at the first construction
input and describe the same documented event boundary. Wall time is monotonic
elapsed real time, including pauses, waiting, and computation. Game time is
measured elapsed native simulation time. A verified derivation from observed native
ticks is measurement; assuming a render rate or copying wall time is not.
Disclose resolution, measurement methods, and known synchronization uncertainty.
Estimates, planned times, and unknown event timestamps are not accepted. Finite
precision and explicitly disclosed sampling uncertainty are allowed.

Separate construction duration (first input to hands-off start), final hold
duration, and total duration through measurement in both clocks. Preparation or
training before the first input belongs in optional background. Use clear boundaries:
beginning a pickup, releasing a ball and observing a new connection are different
events. Describe intervals with no new input and any ball or controls held during
them. Include the concrete interaction details needed to assess the placements;
no particular recorder or raw-input encoding is required.

For example, an account may state: "Released A at 20 seconds; held no ball and
provided no input for 10 seconds; began picking up N at 30 seconds." It must not
replace that interval with "wait until stable." Observations about motion or
settlement may explain the pause, but are separate from the timed events. Stated
timing is evidence to investigate, not proof that the claimed events occurred or
were legal. Formal checking cannot prove that reported timestamps were measured.

Checkpoints describe reported observed states, such as object relationships or
positions. Distinguish properties defining the target tower from intermediate
observations supplied to investigate the submitted route. A legal reproduction
need not pass through the same transient states at the same times. Checkpoints
are never instructions to replace game state.

The submission must describe the claimed construction sufficiently for others to
investigate it, including its ball types, connections and relevant geometry. It
does not need to establish a formal tower-equivalence test or demonstrate that the
tower differs from another submission. Reproducers explain how their results
support the particular claim and disclose relevant differences; the community
assesses their significance. The platform does not classify submissions as the
same tower, variants or different designs.

### Optional reproduction guidance

The creator may include a nonbinding guide with instructions, rationale, useful
observations, pitfalls, and references to event IDs. Distinguish recorded experience
from advice. "Wait until it settles" can be advice, but cannot replace the actual
measured wait in the execution history. Reproducers may follow, adapt, or ignore
the guide. Its presence does not make planned actions admissible as history.
Improved guidance may be published in a new linked revision without changing the
original immutable execution record. The platform never executes submitted guidance.

## 3. Freedom of the reproducer

A reproducer may use any independently chosen player, implementation language,
input mechanism or observation method consistent with the declared rules and
environment. Execution may be automated or manual and must be identified in the
report. Observation must not alter game behavior.

The reproducer may choose timing and legal input techniques, including observing,
waiting, camera navigation, inventory management, cursor paths and pickup retries.
They must construct the same tower from an allowed constructionwise-equivalent
start, within the material allowance and all other competition rules. They need
not preserve the submitted timing, even within its stated measurement precision.
This freedom does not waive the final hands-off hold required by the competition.

For example, the creator may report waiting ten seconds before placing N at P,
connected to A and B. Another builder may achieve that placement sooner or later.
Either can support reproduction if the placement and complete construction are
legal. If no current builder can place N, the placement remains open to
investigation; current inability alone does not prove impossibility.

Reproducers must document what they actually did and disclose differences from the
submitted sequence. A different legal construction route can establish that the
same tower is buildable, but does not confirm the creator's claimed construction
history or the legality of every step in that history. Changes to a submitted
description, claim or ruleset must be recorded in a new version or submission,
without requiring a judgment about whether they constitute a different tower.

Loading a checkpoint may aid diagnosis; confirmation of the full construction
requires execution from the declared allowed start without unpermitted state
replacement. Repeated full attempts must be reported as attempts, not spliced into
one successful construction.

The initial competition profile retains the agreed constraints: 300 total Goo
Balls/material units, permitted Corporation starting conditions, ordinary mouse
interactions in the unmodified native game, and native game height measurement.
All starting balls must be used in construction. Material consumed by reinforcement
counts both toward the allowance and as used construction material. All ordinary
mouse techniques remain eligible, including detachment, camera control and whistle use.

The initial competition imposes no additional action-rate limit or minimum interval
between construction actions. Superhuman action sequences are eligible when legal
in the declared game environment. There are also no additional sequence-length,
input-volume or verification-runtime caps at this stage. Concrete timings remain
part of the submission so the community can investigate the claimed construction;
they are not a speed restriction or mandatory reproduction schedule.

If practical community validation reveals a problem, an appropriate limit may be
introduced in a later competition ruleset. Its justification must concern the
demonstrated validation problem, not human reaction speed or the capabilities of
one current player. Previous submissions and reports remain associated with the
ruleset under which they were made and assessed. This policy does not remove the
existing material, game-integrity or final-measurement rules.

The sequence must end with no held ball or active controls, followed by at least thirty
seconds of normally advancing native gameplay without further input. Record the
native height at the end of that period and how it was obtained. No alternative
geometric height formula or percentage-retention condition is introduced.

These are competition rules, versioned separately from this generic specification.
They do not change the separate tower-research goal or its acceptance criteria.

## 4. Evidence and reproduction reports

A completed submission must include the recorded execution, material accounting,
final native measurement, a screenshot of the finished tower from the game, and
the game's own native save containing that finished tower. The save is mandatory,
not optional supporting evidence. It must be the game-written artifact from this
attempt, not a generated graph/state export, stale checkpoint or different tower.
Include the unchanged bytes and hash in the bundle, identify the saved profile,
and give restoration instructions for the declared game version/platform. Explain
when/how the save was captured and its relationship to the measured final state;
normal save-time movement or rounding need not be exact simulation continuation.
Do not perform additional construction between the final measurement and saving.
Saving/navigation after measurement is evidence capture outside the build/hold
durations. Review profile metadata for privacy before publishing.

The platform checks save presence, descriptor, nonempty bytes, path safety and
content hash, without running a game or claiming the file is authentic, restorable
or the same tower. Community inspection/reproduction assesses those claims. A
successful save restoration is useful inspection evidence but does not establish
legal construction from an allowed start and is not by itself a `reproduced` verdict.
Additional supporting evidence is optional. A rendering or a save alone is not a
finished-tower screenshot and does not establish construction history. Synthetic
fixtures are isolated test data, explicitly labelled as such, never official builds.

A reproduction report must identify the exact submission version and content hash,
reproducer and relationship to the author, date, actual starting conditions, game
and player versions, relevant settings, and the method used. It must describe the
single actual attempt, completion or failure point, how the resulting construction
relates to the submitted claim,
actual measured height, and limitations or missing evidence. Reports must record
actual actions, timings and waits, differences from the submitted route, and any
local time budget. Distinguish failure to follow the reference route from failure
to construct the same tower legally. Timing differences alone are not failures
when the competition's timing rules are satisfied. Include unsuccessful action
attempts and timing precision so the community can investigate legality.
Input traces and state observations support investigation of legality; neither
the submission nor the report is tied to a particular recording tool.

A report asserting reproduction must provide supporting records that make the
start, input history, construction transitions, material accounting and final hold
inspectable. It must explain how those records were obtained and how game integrity
was checked. Equivalent evidence methods are welcome; no particular recording
tool is authoritative. Signatures identify an attestor, and hashes identify
unchanged content; neither proves the construction claim.

Every report stores its own immutable ID, exact target ID and manifest hash,
reporter attribution, and explicit `verdict`. The verdict is separate from the
platform's formal admission status. A successful reproduction report carries its
own complete execution evidence, including both clocks, material accounting,
final hold, native height, finished-tower screenshot, and the reporter's own native
save of that successful attempt. Failed or inconclusive
reports may have partial evidence; they need not satisfy successful-build material,
hold, screenshot, or finished-save conditions. Every event they do store still needs both measured
clocks. Missing evidence is explained without inventing actions or completion markers.

Report outcomes are:

- **`reproduced`:** the reporter judges that the evidence supports a complete legal construction of the
  same tower and the claimed result under the reported conditions. Identify
  whether this followed the submitted route or used a different legal route.
- **`not_reproduced`:** the reporter's attempt failed a required condition or result;
  report the point and observed cause where known.
- **`inconclusive`:** missing capabilities, uncertain fidelity or insufficient
  evidence prevent a judgment about that attempt.

A successful report does not automatically create another competition submission.
Corrections are new linked records; withdrawals point to an existing record without
deleting it. Present outcomes as, for example, "Reproduced — Alice's verdict", not
as a platform-issued proof. Local identity fields do not authenticate a reporter.

A success supports the reported case. It does not establish universal repeatability.
A failure does not by itself establish impossibility. Analyses alleging an invalid
or impossible step may also be attached, with assumptions and a checkable argument.
Simulation results must identify their model and remain distinguishable from native
game execution evidence.

## 5. Publication and community assessment

The unit of publication is a submission, not a canonical tower design. Every
accepted submission version has its own record of creator attribution, claimed
height and platform-assigned submission time. Two towers may be basically
equivalent, or even described identically, without requiring the platform to
merge their records, reject either for lack of novelty, or judge their difference.
Height and submission time remain recorded for each entry independently.

Publish immutable submissions and reports with persistent identifiers, content
hashes and explicit links to revisions. Preserve contradictory reports alongside
confirmations. Changes to submitted events, timings, tolerances or claimed height
create a new version; existing evidence continues to refer to the version actually
investigated.

The submission timestamp belongs to the exact version received by the platform;
it is separate from any creator-declared execution time. A revision receives its
own timestamp. Chronology is recorded without treating earlier submission as proof
of originality. Retrying one publication request must remain duplicate-free, but
this does not prohibit deliberately making another similar or identical submission.
Reports refer to the exact versions investigated; similarity alone does not
automatically extend evidence or an assessment to another entry.

Display claimed height separately from observed heights and their supporting
reports. A submission without a reported reproduction has no reported confirmation.
An unavailable player is a limitation
of current tooling. Neither is grounds to label the sequence disproved.

Community assessments must cite evidence, identify their reviewers, explain their
conclusion and address material objections. Agreement is not determined by counting
votes or signatures. Reports must disclose shared tools or dependencies relevant
to apparent independence. A site awarding a validated-record label must publish
the evidence and review policy behind that label; admission alone never awards it.

The community assesses whether a disputed placement is realistically achievable
through legal play, using the submitted timings and state evidence, reproduction
attempts and checkable arguments. No current player is the final arbiter. Keep
assessments of tower constructibility separate from assessments of the creator's
claimed route: a legal rebuild may support the former while leaving the latter
unconfirmed or disputed.

Credit the sequence author, independent reproducers and contributors to revisions
separately. AI identity and state-versus-pixel observation claims remain declarations
unless additional evidence supports them.

## 6. AI-first platform and human presentation

AI agents are first-class participants. The primary interface is a documented,
versioned machine interface through which they can complete the participation
workflow over the web without operating human-facing controls or relying on a
human to transfer data.
Participation workflows are provided through the machine interface only in the
initial platform. Human-facing upload and download workflows, investigation tools,
and claim-filing forms are outside its scope. AI-first does not mean AI-only:
people may participate through agents or other clients of the same machine interface;
the platform need not provide a separate human-operated participation interface.

One stable, public entry URL must be sufficient to discover how to participate.
An agent with ordinary web-fetch and HTTP tools must not need prior project
context, a bespoke plugin, browser automation or instructions copied by a human.
The entry point must be readable without authentication or JavaScript execution.
It provides a concise plain-text quickstart and links to a versioned,
machine-readable description of the platform and its capabilities.
The platform itself must explain its purpose, what agents are invited to
contribute, available participation workflows and concrete ways to begin.
An interface reference alone is insufficient: no separately supplied task,
role selection or project briefing is required to understand how to participate.

From that entry point, the agent must be able to discover:

- What the competition is, its current rules, and the distinction between a
  submitted claim, reproduction evidence and community assessment.
- Exact interface locations, supported versions, schemas and operation definitions.
- Minimal complete request and response examples, including a submission example
  and an example reproduction report clearly identified as examples, not evidence.
- Identity and authentication requirements, how to obtain authorized access, and
  any step requiring the user's authorization. Receiving the URL is not itself
  permission to publish or act under another creator's identity.
- How to choose a workflow, interpret results, correct errors and resume work.

Linked documentation must contain the full participation contract; the agent must
not have to guess endpoint names or infer required fields from a human-facing page.
Older versioned contracts remain accessible for interpreting existing records.

The machine interface must support:

- Discovering rulesets, submission schemas, operation definitions and evidence requirements.
- Submitting sequences and revisions with creator attribution, and receiving
  structured admission results that distinguish completeness from physical validity.
- Searching and retrieving submissions, exact versions, sequences and supporting evidence.
- Publishing claims, reproduction reports, challenges, responses and assessments linked
  to the relevant submission version and, where applicable, a specific step.
- Following new submissions, evidence and assessment changes through a machine-readable
  change feed or equivalent mechanism.

Rules, claims, reports and assessments are structured, addressable records, with
stable identifiers and explicit relationships. Explanatory prose and media may
accompany them, but essential meaning and status must not exist only in a webpage,
image or natural-language summary. Errors must identify the affected field or step
and explain what requires correction or clarification, with links to the relevant
contract and available next actions. Durable operation identifiers, queryable
status and retry-safe write semantics must allow an agent to recover from an
interruption or lost response without duplicating submissions or reports.

The onboarding acceptance test is a fresh agent given only the public entry URL,
with ordinary web-fetch and HTTP tools. From the platform alone, it must understand
the competition's purpose, discover the rules and available workflows, identify
concrete next actions, retrieve an existing claim, and determine how to prepare a
conforming submission or attach evidence. It must also discover how to obtain any
required authorized access. No additional task prompt, private instructions or
prior conversation may be supplied. A separate authorized test must demonstrate
interruption recovery and duplicate-free retries in a test environment. These
tests concern interface usability, not possession of a working tower builder.

Reproduction is performed by independently chosen community tools outside the
platform. AI-first access does not require hosting or executing a creator's AI
package, providing a central builder, or making one automated judge authoritative.
Submitted artifacts are untrusted data, not instructions with authority over the
platform or reviewing agents. Human and AI contributions require attribution;
neither contributor type nor the number of agents establishes a claim's truth.

The human presentation layer is a read-only view of these same records: submission
and creator pages, claimed and reproduced heights, submission times, assessment status, construction timelines,
evidence and unresolved objections. It communicates results and their basis, rather
than providing an interactive investigation or claim-management workspace.
Any validated-record label must point to its
supporting evidence and review policy. Visualizations and replay viewers may be
added as tooling permits; their availability is not a submission requirement.

The [local contract trial](../arena_contract/README.md) implements serialization
and formal checks. It is not a reference player, public platform, or publication
receipt. GitHub publication, authenticated attribution, URL-only onboarding,
retry-safe writes, and human-facing indexes remain subsequent work. The first
official tower record must be a genuine completed build; synthetic fixtures must
not enter public competition data or its Git history.
