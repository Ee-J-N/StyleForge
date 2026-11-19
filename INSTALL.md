# Install StyleForge

## Requirements

- Python 3.11 or later.
- Codex with Skill discovery, or another Agent that can read `SKILL.md` and run the local Python CLI.
- Pillow for screenshot validation and Windows desktop/terminal pixel capture.
- Playwright plus its Chromium browser for local browser screenshots.
- `python-docx` and `pypdf` for `.docx` and `.pdf` style samples.
- Native host tools such as PowerShell, Bash, Node.js, Ruby or Perl only when executing an EXP with that extension.

The CLI uses the Python standard library and requires no web service, database server or MCP server for persistence. An external browser/desktop capture tool can supply a screenshot through `evidence-import`; its host receipt is recorded separately from native Playwright capture.

## Install In A Codex Skills Directory

Install the entire directory as `styleforge` under the active Codex skills root, preserving `SKILL.md`, `agents/`, `scripts/` and `references/`:

```powershell
$skillsRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills' } else { Join-Path $HOME '.codex\skills' }
$skillPath = Join-Path $skillsRoot 'styleforge'
New-Item -ItemType Directory -Force -Path $skillsRoot | Out-Null
Copy-Item -LiteralPath '<project-root>' -Destination $skillPath -Recurse
```

Use a fresh target directory for the initial copy. When updating an installed Skill, preserve user data in `%LOCALAPPDATA%\StyleForge`; it is not stored inside the Skill directory. The development checkout may remain in any path for CLI use.

Install the supported optional dependencies from an activated Python environment:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python scripts/styleforge.py --version
python scripts/styleforge.py probe
```

The first two commands install runtime and test libraries. Install Chromium only when the Playwright browser route is needed. `probe` reports local Playwright/browser/desktop capability; it does not confirm a remote tool service or target.

## Data And Tools

- Personal data defaults to `%LOCALAPPDATA%\StyleForge\users\<local-user>`. Set `--store` to a specific owner-isolated data root when operating multiple environments. `--user` selects a separate data owner ID; it does not alter OS credentials.
- A case stores its selected inputs, hash-linked `events.jsonl`, screenshot evidence, captured command output, EXP snapshots and publication revisions. Keep the entire case folder together for local recovery.
- `case-init --input` copies selected files into the case. `exp-check` snapshots the selected script before execution and runs the snapshot with its registered native interpreter.
- `capture --kind browser` requires a locally installed Playwright Chromium and a reachable HTTP(S) page within the authorized lab. Desktop and terminal screenshots use visible Windows windows and Pillow.
- `terminal-run` requires `conhost.exe` and Windows PowerShell. It executes the exact argv in a new visible real console, preserves raw output, captures that console, and closes only the launched process tree.
- `evidence-import` keeps the supplied image and declared source. It marks capture verification only when the user supplies a host receipt that matches the image hash and names an actual tool call.
- Generic command execution records actual stdout, stderr and exit status. A run becomes `passed` only with exit code zero and a non-empty match for an explicit result pattern. `exp-check` additionally binds the run to the EXP path and content hash.

## Invoke

After the directory is available to Codex's Skill loader, invoke `$styleforge` and specify the case mode, profile, challenge inputs, and authorized CTF/lab scope. For direct CLI use:

```powershell
python '<project-root>\scripts\styleforge.py' --help
```

For API agents, call the CLI as an argv array and preserve its JSON stdout, process exit code and output paths. Never execute a CLI command assembled through a shell string when the local process API accepts argv directly.
