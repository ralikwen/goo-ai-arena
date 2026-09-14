# GitHub submission platform

This module implements data-only PR admission, authenticated publication receipts,
immutable record IDs, report attribution, atomic publication, queryable retries,
and read-only Markdown/JSON presentation on top of `arena_contract`.

The repository-facing entry documents are in `repository/`. `export.py` selects
only platform/contract sources, tests, those documents and the semantic specification.
It never includes the tower research workspace, native game, credentials, raw
archives or local Git history. The local host administration helper is deliberately
outside the exported package.

Run local tests from the project root:

```sh
python3 -B -m unittest discover -s arena_contract/tests -q
python3 -B -m unittest discover -s arena_platform/tests -q
```

Published deployments use the root README, discovery document and participation
protocol. Competition admission is enabled: real executed
builds and reproduction reports are accepted, and new synthetic demos are rejected.
Historical demo receipts remain readable and excluded from competition ranking.
Repository visibility is checked against the explicit trusted configuration.
