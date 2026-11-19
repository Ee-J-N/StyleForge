"""Independent session axes, append-only case journals and real command runs."""

from __future__ import annotations

import ast
import importlib.util
import json
import ntpath
import os
import posixpath
import re
import shutil
import subprocess
import sys
import time
import tokenize
import uuid
from pathlib import Path

from sf_core import SCHEMA, append_event, child, copy_original, file_hash, load_events, lock, now, readable_name, read_json, write_json, write_text


def _script_runtime(path):
    suffix = Path(path).suffix.lower()
    candidates = {
        ".py": (sys.executable, ()),
        ".js": (shutil.which("node"), ()),
        ".sh": (shutil.which("bash"), ()),
        ".rb": (shutil.which("ruby"), ()),
        ".pl": (shutil.which("perl"), ()),
    }
    if suffix == ".ps1":
        executable = shutil.which("pwsh") or shutil.which("powershell")
        return (executable, ("-NoProfile", "-File"))
    if suffix not in candidates:
        raise ValueError(f"No verified EXP runner is defined for {suffix or 'extensionless files'}")
    executable, prefix = candidates[suffix]
    if not executable:
        raise ValueError(f"The required EXP interpreter is unavailable for {suffix}")
    return executable, prefix


def _command_executes_script(command, path):
    executable, prefix = _script_runtime(path)
    if not command or Path(command[0]).resolve() != Path(executable).resolve():
        return False
    script_index = 1 + len(prefix)
    if tuple(command[1:script_index]) != prefix or len(command) <= script_index:
        return False
    try:
        return Path(command[script_index]).resolve(strict=True) == Path(path).resolve(strict=True)
    except OSError:
        return False


def _recorded_path_key(value):
    value = str(value)
    if re.match(r"^(?:[A-Za-z]:[\\/]|\\\\)", value):
        return ntpath.normcase(ntpath.normpath(value))
    return posixpath.normpath(value)


def _recorded_command_executes_script(command, path):
    """Check archived argv shape without requiring its interpreter on this machine."""
    if not isinstance(command, (list, tuple)) or not command:
        return False
    suffix = Path(path).suffix.lower()
    interpreter_names = {
        ".js": {"node", "node.exe"},
        ".sh": {"bash", "bash.exe"},
        ".rb": {"ruby", "ruby.exe"},
        ".pl": {"perl", "perl.exe"},
    }
    prefix = ("-NoProfile", "-File") if suffix == ".ps1" else ()
    if suffix == ".py":
        basename = re.sub(r"\.exe$", "", ntpath.basename(str(command[0])).casefold())
        interpreter_matches = bool(re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", basename))
    else:
        allowed = ({"pwsh", "pwsh.exe", "powershell", "powershell.exe"} if suffix == ".ps1"
                   else interpreter_names.get(suffix, set()))
        basename = str(command[0]).replace("\\", "/").rsplit("/", 1)[-1].casefold()
        interpreter_matches = basename in allowed
    script_index = 1 + len(prefix)
    if (not interpreter_matches or tuple(str(arg).casefold() for arg in command[1:script_index])
            != tuple(arg.casefold() for arg in prefix) or len(command) <= script_index):
        return False
    return _recorded_path_key(command[script_index]) == _recorded_path_key(path)


def _register_exp_input(ctx, case_id, source):
    """Snapshot the exact bytes of an explicitly selected EXP into this case."""
    source = Path(source).resolve(strict=True)
    if not source.is_file():
        raise ValueError(f"Expected an EXP file: {source}")
    checksum = file_hash(source)
    folder = ctx.case_dir(case_id)
    case = ctx.case(case_id)
    for entry in case["inputs"]:
        existing = child(folder, entry["path"])
        if existing == source and file_hash(existing) == checksum:
            return existing, source
        if Path(entry["source"]).resolve() == source and entry["sha256"] == checksum:
            if existing.is_file() and file_hash(existing) == checksum:
                return existing, source
    prefix = f"{checksum[:16]}-"
    target = child(folder, "inputs", "exp", prefix + readable_name(source.name))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if file_hash(target) != checksum:
            raise ValueError(f"EXP snapshot path already contains different bytes: {target}")
    else:
        copied = copy_original(source, target.parent, prefix)
        if copied != target or file_hash(copied) != checksum:
            raise ValueError("EXP changed while its case snapshot was being created")
    if file_hash(source) != checksum:
        raise ValueError("EXP changed while its case snapshot was being created")
    case["inputs"].append({"source": str(source), "path": target.relative_to(folder).as_posix(),
                           "sha256": checksum, "role": "selected_exp"})
    write_json(folder / "case.json", case)
    return target, source


def init_case(ctx, case_id, title, category, profile_id=None, style_mode="write", record_mode="replay", inputs=()):
    folder = ctx.case_dir(case_id)
    if folder.exists():
        raise ValueError("Case exists; use case-switch to change one dimension")
    if profile_id:
        ctx.profile(profile_id)
    parent = folder.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".{folder.name}.init-{uuid.uuid4().hex}"
    case = {"schema_version": SCHEMA, "id": case_id, "owner_user": ctx.user, "title": title,
            "category": category, "style_mode": style_mode, "record_mode": record_mode, "profile_id": profile_id,
            "created_at": now(), "inputs": [], "revisions": []}
    committed = False
    try:
        staging.mkdir()
        for source in inputs:
            source = Path(source).resolve(strict=True)
            files = sorted(p for p in source.rglob("*") if p.is_file()) if source.is_dir() else [source]
            for path in files:
                relative = path.relative_to(source) if source.is_dir() else Path(path.name)
                destination = child(staging, "inputs", source.name if source.is_dir() else "files", *relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    raise ValueError(f"Duplicate input name: {destination}")
                shutil.copy2(path, destination)
                case["inputs"].append({"source": str(path), "path": destination.relative_to(staging).as_posix(),
                                       "sha256": file_hash(destination)})
        write_json(staging / "case.json", case)
        write_json(staging / "evidence" / "manifest.json", {"schema_version": SCHEMA, "owner_user": ctx.user, "case_id": case_id, "evidence": []})
        with lock(parent):
            if folder.exists():
                raise ValueError("Case exists; use case-switch to change one dimension")
            os.rename(staging, folder)
            committed = True
        append_event(ctx, case_id, "session", "开始记录：" + ("本轮首次解题。" if record_mode == "solve" else "对已有材料进行复现，以下新运行不代表首次解题。"))
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        if committed and folder.exists():
            shutil.rmtree(folder)
        raise
    return case


def switch(ctx, case_id, style_mode=None, record_mode=None, profile_id=None):
    case = ctx.case(case_id)
    before = {key: case[key] for key in ("style_mode", "record_mode", "profile_id")}
    if style_mode:
        case["style_mode"] = style_mode
    if record_mode:
        case["record_mode"] = record_mode
    if profile_id:
        ctx.profile(profile_id)
        case["profile_id"] = profile_id
    write_json(ctx.case_dir(case_id) / "case.json", case)
    append_event(ctx, case_id, "mode_change", "切换工作维度；既有事件与截图保持原始来源。", before=before,
                 after={key: case[key] for key in before})
    return case


def record(ctx, case_id, kind, text, basis=None, artifact=None, historical=False):
    folder = ctx.case_dir(case_id)
    events = load_events(folder)
    if basis and basis not in {e["id"] for e in events}:
        raise ValueError("Unknown basis step")
    if kind in ("judgement", "result") and not basis and not artifact:
        raise ValueError("A judgement or result needs a basis step or an actual source file")
    details = {"basis_step": basis, "status": "inferred" if kind == "judgement" else "recorded"}
    if artifact:
        path = copy_original(artifact, folder / "history", uuid.uuid4().hex[:8] + "-")
        details.update(artifact=path.relative_to(folder).as_posix(), artifact_sha256=file_hash(path))
    if historical:
        if not artifact:
            raise ValueError("Historical records require their source file")
        details.update(origin="user_history", status="user_provided")
    return append_event(ctx, case_id, kind, text, **details)


def run(ctx, case_id, command, cwd=None, timeout=60, text="运行并记录实际命令。", result_pattern=None, script=None):
    if not command or any(not isinstance(argument, str) or not argument for argument in command):
        raise ValueError("An explicit command argument array is required")
    if timeout <= 0 or timeout > 3600:
        raise ValueError("Timeout must be between 1 and 3600 seconds")
    if result_pattern:
        try:
            re.compile(result_pattern)
        except re.error as error:
            raise ValueError(f"Invalid result validation pattern: {error}") from error
    folder = ctx.case_dir(case_id)
    ctx.case(case_id)
    workdir = Path(cwd).resolve(strict=True) if cwd else folder
    script_path = Path(script).resolve(strict=True) if script else None
    script_hash = file_hash(script_path) if script_path else None
    if script_path and not _command_executes_script(command, script_path):
        raise ValueError("The executed command must pass the selected EXP as its interpreter's script file")
    run_id = "run-" + uuid.uuid4().hex[:12]
    log_dir = folder / "runs" / run_id
    log_dir.mkdir(parents=True)
    script_snapshot = None
    try:
        if script_path:
            script_snapshot = copy_original(script_path, log_dir / "inputs")
            if file_hash(script_snapshot) != script_hash:
                raise ValueError("EXP changed while the run snapshot was being created")
    except Exception:
        shutil.rmtree(log_dir)
        raise
    started = now()
    began = time.monotonic()
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    # File-backed streams preserve complete raw output and avoid unbounded RAM use.
    try:
        with (log_dir / "stdout.bin").open("wb") as stdout, (log_dir / "stderr.bin").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=workdir, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       env=environment, shell=False)
            timed_out = False
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                else:
                    process.kill()
                process.wait(timeout=15)
                returncode = process.returncode
    except Exception:
        shutil.rmtree(log_dir)
        raise
    raw_stdout = (log_dir / "stdout.bin").read_bytes()
    raw_stderr = (log_dir / "stderr.bin").read_bytes()
    decoded = raw_stdout.decode("utf-8", errors="replace")
    decoded_error = raw_stderr.decode("utf-8", errors="replace")
    write_text(log_dir / "stdout.txt", decoded)
    write_text(log_dir / "stderr.txt", decoded_error)
    combined_output = decoded + ("\nSTDERR:\n" + decoded_error if decoded_error else "")
    results = [m.group(0) for m in re.finditer(result_pattern, combined_output)] if result_pattern else []
    execution_status = "timed_out" if timed_out else ("passed" if returncode == 0 else "failed")
    result_status = "not_requested" if not result_pattern else ("passed" if results else "failed")
    current_script_hash = file_hash(script_path) if script_path else None
    script_integrity = "passed" if script_path and current_script_hash == script_hash and file_hash(script_snapshot) == script_hash else ("failed" if script_path else "not_applicable")
    status = "passed" if execution_status == "passed" and result_status == "passed" and script_integrity in ("passed", "not_applicable") else "unverified"
    if execution_status != "passed" or script_integrity == "failed" or result_status == "failed":
        status = "timed_out" if timed_out else ("failed" if execution_status != "passed" else "validation_failed")
    report = {"run_id": run_id, "command": list(command), "cwd": str(workdir), "started_at": started,
              "finished_at": now(), "duration_seconds": round(time.monotonic() - began, 3), "exit_code": returncode,
              "timed_out": timed_out, "status": status, "execution_status": execution_status,
              "result_validation": {"status": result_status, "pattern": result_pattern, "matches": results},
              "stdout": (log_dir / "stdout.txt").relative_to(folder).as_posix(),
              "stderr": (log_dir / "stderr.txt").relative_to(folder).as_posix(),
              "stdout_sha256": file_hash(log_dir / "stdout.bin"), "stderr_sha256": file_hash(log_dir / "stderr.bin"),
              "result_matches": results, "result_scope": "observed output; correctness still requires challenge-specific checks"}
    if script_path:
        report.update(script_path=str(script_path), script_sha256=script_hash,
                      script_sha256_after= current_script_hash,
                      script_integrity=script_integrity,
                      script_snapshot=script_snapshot.relative_to(folder).as_posix())
    write_json(log_dir / "run.json", report)
    event = append_event(ctx, case_id, "run", text, **report, output_excerpt=(decoded + ("\nSTDERR:\n" + decoded_error if decoded_error else ""))[:6000])
    report["step_id"] = event["id"]
    return report


def exp_check(ctx, case_id, path, execute=False, cwd=None, timeout=60, result_pattern=None, script_args=()):
    source_file = Path(path).resolve(strict=True)
    path, source_file = _register_exp_input(ctx, case_id, source_file)
    checksum = file_hash(path)
    report = {"file": str(path), "source_file": str(source_file), "sha256": checksum,
              "case_input": path.relative_to(ctx.case_dir(case_id)).as_posix(),
              "source_sha256": file_hash(source_file),
              "syntax": "not_checked", "warnings": [], "runtime": "not_run", "status": "not_executed"}
    if path.suffix.lower() == ".py":
        with tokenize.open(path) as stream:
            source_text = stream.read()
        tree = ast.parse(source_text, filename=str(path))
        report["syntax"] = "passed"
        modules = set()
        defined = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules.add(node.module.split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    report["warnings"].append(f"Empty definition: {node.name}")
            if isinstance(node, ast.Constant) and node.value is Ellipsis:
                report["warnings"].append(f"Ellipsis at line {node.lineno}; review for omitted logic")
        for module in sorted(modules):
            local = path.parent / (module + ".py")
            package = path.parent / module / "__init__.py"
            if not local.exists() and not package.exists() and importlib.util.find_spec(module) is None:
                report["warnings"].append(f"Dependency not found in this interpreter: {module}")
        report["imports"] = sorted(modules)
        report["definitions"] = sorted(defined)
        report["manual_review_required"] = ["variable/function resolution", "all external inputs and paths", "complete algorithm and payload", "output semantics and challenge result"]
    else:
        report["warnings"].append("Use the actual language toolchain; no Python syntax claim was made")
    if execute:
        executable, prefix = _script_runtime(path)
        actual = [executable, *prefix, str(path), *script_args]
        if file_hash(source_file) != checksum or file_hash(path) != checksum:
            raise ValueError("Selected EXP differs from the case snapshot; refresh the selected EXP before running")
        report["runtime"] = run(ctx, case_id, actual, cwd or path.parent, timeout,
                                "运行选定 EXP，并核对本轮原始输出。", result_pattern, script=path)
        if file_hash(path) != checksum or file_hash(source_file) != checksum:
            report["status"] = "validation_failed"
            report["runtime"]["script_integrity"] = "failed"
            report["warnings"].append("Selected EXP changed during or after execution")
        else:
            report["status"] = report["runtime"]["status"]
    report["sha256_after"] = file_hash(path)
    if report["sha256_after"] != checksum:
        report["status"] = "validation_failed"
        report["warnings"].append("Selected EXP changed after static inspection")
    append_event(ctx, case_id, "exp_check", "检查最终 EXP；静态检查与实际运行分别记录。", report=report)
    return report
