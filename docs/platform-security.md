# Security boundary and trial limitations

The hosted workflow uses `pull_request_target` only to run trusted default-branch
code. It never checks out, imports, installs, evaluates or executes code from the
pull request. The complete Git tree delta is inspected: one new bundle, regular
non-executable blobs only. Non-data changes need maintainer review.

The checking job has read-only repository permissions. Its API token is supplied
only to the data-fetching step; the validator runs in the next step without that
token in its environment. Checkout credentials are not persisted. Submitted JSON,
JSONL, images, native saves, links and guides are data, not executable instructions. No external
evidence URLs or submitted schema references are fetched. Image decoding uses the
trusted network-disabled adapter. No host credentials or competitor tokens are
stored in GitHub Actions secrets.

Required native saves are hashed opaque bytes with a nonempty-file and descriptor
check, not game-loaded validation. No submitted save parser, restore command or
native game is run. Restorability, correspondence with the claimed final tower and
construction legality remain unverified by admission. Community restoration must
use a separately authorized isolated test profile; profile saves can contain
personal data and must not implicitly replace an existing player's profile.

Publication runs in a fresh job with its own scoped GitHub Actions token. It
receives only the result JSON, rechecks the PR identity, head SHA, complete data
delta, blob identities, referenced ownership and current base SHA. It reuses Git
blobs by their checked hashes; it does not decode submitted images or event streams.
The admission result is trusted output of the platform checker, not proof of physics.

The new bundle, receipt and catalogue are one commit with the checked main tip as
its sole parent. A non-force ref advance fails on a concurrent divergent write.
Recovery checks the receipt first. The PR is closed only if it still names the
checked head. The platform imports data, not the submitted Git history. A tight
race with a later PR edit can publish the earlier checked snapshot, never the new
unchecked bytes; the receipt makes the exact accepted version explicit.

Actions are pinned to verified full commit SHAs. Dependency versions are fixed in
the trusted workflow; the trial has not yet added full transitive hash locking.
No persistent self-hosted runner is used. A dependency install, API or runner
failure yields pending when feedback can run; a wholly cancelled/outage run may
require explicit recheck. There is no new action-speed or sequence-length game rule.
GitHub itself has file, request, storage and runtime limits; larger evidence and
cost/abuse handling require operational work before broad public launch.

Only data-only requests are auto-admitted. Repository owners retain administrative
access. The public main branch is configured to prohibit force pushes and deletion,
require linear history and apply those protections to administrators. Normal
fast-forward publication commits remain allowed so the scoped Actions token can
publish an admitted bundle atomically. This does not require pull-request approval
for every administrative code change; maintainers should use reviewed changes.

Dependencies have fixed direct versions but are not fully transitively
hash-locked. There is no independent security certification or global abuse queue.
Jobs have bounded runtime; maintainers can pause Actions if abuse or backlog occurs.
A concurrent publication may require an explicit recheck. These limitations are
operational and do not change the competition rules.

The public repository starts with a clean platform export and a genuine first
build. Private trial records, synthetic publication receipts and private Git history
are not imported. Synthetic fixture generators remain only for local tests.
