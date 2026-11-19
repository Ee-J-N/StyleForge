# Install StyleForge

## Requirements

- Python 3.11 or later.
- Codex with Skill discovery, or another Agent that can read `SKILL.md` and run the local Python CLI.
- Pillow for screenshot validation and Windows desktop/terminal pixel capture.
- Playwright plus its Chromium browser for local browser screenshots.
- `python-docx` and `pypdf` for `.docx` and `.pdf` style samples.
- Native host tools such as PowerShell, Bash, Node.js, Ruby or Perl only when executing an EXP with that extension.

The CLI uses the Python standard library and requires no web service, database server or MCP server for persistence. An external browser/desktop capture tool can supply a screenshot through `evidence-import`; its host receipt is recorded separately from native Playwright capture.

## Keep The Skill On D:

This repository is itself the installable Skill. Keep the checkout at `D:\AI\codex\styleforge` and use that directory directly. If the host requires a separate skills root, configure a D-drive root and copy the entire folder there; do not install a second copy under the Windows profile on C:.

```powershell
$skillsRoot = 'D:\AI\codex\.codex\skills'
$skillPath = Join-Path $skillsRoot 'styleforge'
New-Item -ItemType Directory -Force -Path $skillsRoot | Out-Null
robocopy 'D:\AI\codex\styleforge' $skillPath /E /XD .git .venv .pip-cache .test-tmp .pytest_cache __pycache__ styleforge-data
if ($LASTEXITCODE -ge 8) { throw "Skill copy failed with robocopy code $LASTEXITCODE" }
```

Use a fresh target directory for the initial copy. When updating an installed Skill, preserve user data in `D:\AI\codex\StyleForgeData`; it is not stored inside the Skill directory.

Create the Python environment, package cache and optional browser cache on D:

```powershell
$projectRoot = 'D:\AI\codex\styleforge'
$env:PIP_CACHE_DIR = Join-Path $projectRoot '.pip-cache'
$env:TEMP = Join-Path $env:PIP_CACHE_DIR 'tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
$env:STYLEFORGE_BROWSERS_HOME = 'D:\AI\codex\StyleForgeData\playwright-browsers'
$env:PLAYWRIGHT_BROWSERS_PATH = 'D:\AI\codex\StyleForgeData\playwright-browsers'
python -m venv (Join-Path $projectRoot '.venv')
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
& $python -m pip install -r (Join-Path $projectRoot 'requirements-dev.txt')
& $python -m playwright install chromium
& $python (Join-Path $projectRoot 'scripts\styleforge.py') --version
& $python (Join-Path $projectRoot 'scripts\styleforge.py') probe
```

The pip command installs runtime and test libraries. Install Chromium only when the Playwright browser route is needed. `probe` reports local Playwright/browser/desktop capability; it does not confirm a remote tool service or target.

## Data And Tools

- Personal data defaults to `D:\AI\codex\StyleForgeData\users\<local-user>`. Set `--store` or `STYLEFORGE_DATA_HOME` to a specific owner-isolated D-drive root when operating multiple environments. On Windows, StyleForge rejects C-drive stores.
- A case stores its selected inputs, hash-linked `events.jsonl`, screenshot evidence, captured command output, EXP snapshots and publication revisions. Keep the entire case folder together for local recovery.
- `case-init --input` copies selected files into the case. `exp-check` snapshots the selected script before execution and runs the snapshot with its registered native interpreter.
- `capture --kind browser` requires a Playwright Chromium installed under `D:\AI\codex\StyleForgeData\playwright-browsers` and a reachable HTTP(S) page within the authorized lab. Set `STYLEFORGE_BROWSERS_HOME` to another D: path to change this cache. Browser temp files, desktop/terminal evidence and case outputs are kept under D-drive paths.
- `terminal-run` requires `conhost.exe` and Windows PowerShell. It executes the exact argv in a new visible real console, preserves raw output, captures that console, and closes only the launched process tree.
- `evidence-import` keeps the supplied image and declared source. It marks capture verification only when the user supplies a host receipt that matches the image hash and names an actual tool call.
- Generic command execution records actual stdout, stderr and exit status. A run becomes `passed` only with exit code zero and a non-empty match for an explicit result pattern. `exp-check` additionally binds the run to the EXP path and content hash.

## Invoke

After the directory is available to Codex's Skill loader, invoke `$styleforge` and specify the case mode, profile, challenge inputs, and authorized CTF/lab scope. For direct CLI use:

```powershell
$python = 'D:\AI\codex\styleforge\.venv\Scripts\python.exe'
& $python 'D:\AI\codex\styleforge\scripts\styleforge.py' --help
```

For API agents, call the CLI as an argv array and preserve its JSON stdout, process exit code and output paths. Never execute a CLI command assembled through a shell string when the local process API accepts argv directly.
