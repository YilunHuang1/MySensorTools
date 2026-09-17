# Aorta source and evidence contract

Baseline: vita-robot remote master 291b58055b54a924735604f26b840ab1f22b5427
(2026-09-17). Verify remote master and deployed revision separately on every new
investigation. Read `git show origin/master:path`; a local ROS worktree is not the
latest source. Historical driver snippets in MySensorTools are not current code.

Install MySensorTools from its repository root with `pip install -e '.[analysis]'`.
Its MCAP reader uses embedded ROS CDR / FlatBuffers BFBS / JSON schemas without a
ROS installation. Logical sensor names normally become
`aorta/<group>/pub/<name>`. Inspect the actual channel list; use exact names for
multi-group recordings. `/uwb/data` maps to `uwb/ranging`; vlog batch messages must
be flattened. Never manually reinterpret Aorta payloads as CDR.

Live tools source the deployed `/app/script/env.sh`. Use bounded passive checks
from `docs/TOOLS_GUIDE.md`. Do not stop services, publish control contexts, pair,
write sensor registers or change GPIO as an incidental diagnostic step.

Registration is not data arrival. Source, publish and log timestamps differ.
The schema's shape does not prove physical units: check the publisher/adapter and
deployment. PASS needs actual data and tested acceptance criteria; absent data or
unknown thresholds remain INCOMPLETE. Distinguish source review, offline replay,
synthetic tests and live-device proof in the report.
