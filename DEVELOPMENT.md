# Development Notes

## Layout

```text
SKILL.md                     Agent entrypoint and mode selection
agents/openai.yaml           Codex display metadata
scripts/styleforge.py        CLI parser and dispatch
scripts/sf_core.py           Owner-scoped paths, atomic text/JSON writes, locks, hash-chained journal
scripts/style_profiles.py    Sample parsing, measurements, versioned profiles and explicit feedback
scripts/casebook.py          Cases, mode switches, runtime records and EXP verification
scripts/evidence_capture.py  Browser/window/terminal pixels and evidence manifests
scripts/markdown_links.py    Markdown destinations outside inline/fenced code
scripts/publishing.py        Evidence checks, candidates, approvals and offline bundle verification
scripts/import_siyuan.py     Read-only export of explicitly selected SiYuan content
tests/test_audit_regressions.py
```

The local data store is separate from this source tree and defaults to `D:\AI\codex\StyleForgeData` on Windows. Test stores and temporary files stay in the D-drive checkout and are explicitly marked and isolated. Do not put downloaded challenge content, flags or live case data in test fixtures.

## Main Invariants

- A Style Profile contains one declared author, sample provenance, preserved originals and normalized prose. Measured characteristics and user-stated preferences are separate fields.
- Case style and recording modes are independent. Events record their actual timestamp, source, mode and integrity-chain predecessor.
- EXP execution uses a case-owned byte-for-byte snapshot. Runtime records bind argv, exit code, result pattern, raw stdout/stderr hashes, script snapshot and before/after script hashes. A `passed` result requires a successful process and an explicit non-empty result match.
- Only a `passed` EXP event bound to the current case input and matching raw bytes can support a current Flag claim. A plain `run`, old stdout excerpt, derived text file or missing raw log cannot.
- Screenshot records bind original image hash, owner, case and an existing step. Markdown images must exist in both the candidate and original evidence path. Imported images are distinct from captures verified by an actual browser/desktop backend.
- A publication bundle contains its case snapshot, input copies, hash-linked events, raw run streams, EXP copies, historical artifacts and image evidence. `bundle-check` verifies the recorded argv shape and preserved bytes without the live data store or a currently installed copy of the original interpreter; it verifies archived execution evidence and does not re-execute the EXP.
- A candidate is not a formal publication. `approve` checks a user-provided receipt against the exact article hash, refreshes an article-only candidate edit, rejects other untracked modifications and atomically stages the approved archive.
- External URLs are parsed but not fetched. The automatic checks verify artifacts and provenance, not challenge-specific exploit semantics or whether an overly broad regex is a meaningful result check.

## Test

```powershell
$projectRoot = 'D:\AI\codex\styleforge'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$env:TEMP = Join-Path $projectRoot '.test-tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
& $python -B -X utf8 -m pytest -q -p no:cacheprovider (Join-Path $projectRoot 'tests')
& $python -B (Join-Path $projectRoot 'scripts\styleforge.py') --version
& $python -B (Join-Path $projectRoot 'scripts\styleforge.py') --help
```

The suite uses per-test temporary stores, labelled synthetic sample files and a loopback-only HTML page for real Playwright screenshot capture. It never executes a CTF EXP against a live target. If Playwright's Chromium is unavailable, the screenshot integration test reports a skip; install the browser with `python -m playwright install chromium` before treating browser capture as verified.

The pre-fix reproduction harness and result snapshot remain in a separate local audit workspace. They document the earlier defects and are intentionally immutable historical baseline artifacts; the passing regression tests live here.

Validate the Agent entrypoint in a Codex skill-creator environment with:

```powershell
python <skill-creator-root>\scripts\quick_validate.py <styleforge-directory>
```

Before changing case, profile, evidence or publication persistence, add an isolated regression test for successful use and failure recovery. Preserve existing user stores and candidate bundles; test destructive operations only against a fixture store.
