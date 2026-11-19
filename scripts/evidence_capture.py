"""Capture actual browser/window pixels and preserve provenance, never draw a UI."""

from __future__ import annotations

import importlib.util
import base64
import os
import platform
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from sf_core import append_event, child, copy_original, file_hash, load_events, lock, now, read_json, readable_name, write_json


def browser_candidates():
    candidates = []
    for root in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if root:
            for suffix in ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe"):
                path = Path(root) / suffix
                if path.is_file():
                    candidates.append(str(path))
    for name in ("chromium", "chromium-browser", "google-chrome", "msedge"):
        executable = shutil.which(name)
        if executable:
            candidates.append(executable)
    return list(dict.fromkeys(candidates))


def probe(host_tools=()):
    playwright = importlib.util.find_spec("playwright") is not None
    pillow = importlib.util.find_spec("PIL") is not None
    bundled = None
    if playwright:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as runtime:
            bundled = runtime.chromium.executable_path
    candidates = browser_candidates()
    if bundled and Path(bundled).is_file():
        candidates.insert(0, bundled)
    desktop = os.name == "nt" and pillow
    if desktop:
        import ctypes
        desktop = ctypes.windll.user32.GetSystemMetrics(0) > 0 and ctypes.windll.user32.GetSystemMetrics(1) > 0
    return {
        "probed_at": now(), "platform": platform.platform(),
        "browser": {"available": bool(playwright and candidates), "playwright_installed": playwright, "executables": candidates,
                    "verification": "presence probe; each capture must launch and succeed"},
        "desktop": {"available": bool(desktop), "provider": "Pillow ImageGrab + native Win32 window coordinates", "verification": "presence probe"},
        "terminal": {"available": bool(desktop), "requires": "a visible real terminal window and its title; text logs are separate"},
        "burp_wireshark": {"available": "not_assumed", "requires": "an actual visible application window or a registered host tool"},
        "host_tools": list(host_tools),
        "manual_fallback": "Preserve raw text now; request a user-supplied real screenshot if every actual capture route fails",
    }


def manifest(ctx, case_id):
    result = read_json(ctx.case_dir(case_id) / "evidence" / "manifest.json")
    if result["owner_user"] != ctx.user or result["case_id"] != case_id:
        raise ValueError("Evidence owner or case mismatch")
    return result


def add(ctx, case_id, step_id, source_type, source, operation, caption, file=None, capture_verified=False, error=None):
    folder = ctx.case_dir(case_id)
    if step_id not in {event["id"] for event in load_events(folder)}:
        raise ValueError("Evidence must be associated with an existing real step")
    evidence_id = "evidence-" + uuid.uuid4().hex[:12]
    entry = {"id": evidence_id, "owner_user": ctx.user, "case_id": case_id, "step_id": step_id, "captured_at": now(),
             "source_type": source_type, "source": source, "operation": operation, "caption": caption,
             "capture_verified": capture_verified, "confirmed_by_user": False, "confirmation_ref": None,
             "status": "captured" if file else "unavailable", "path": None, "sha256": None, "error": error}
    if file:
        from PIL import Image
        with Image.open(file) as image:
            width, height = image.size
            image.verify()
        if width < 2 or height < 2:
            raise ValueError("Screenshot is empty or too small")
        original = copy_original(file, folder / "evidence" / "original", evidence_id + "-")
        entry.update(path=original.relative_to(folder).as_posix(), sha256=file_hash(original), width=width, height=height)
    with lock(folder / "evidence"):
        result = manifest(ctx, case_id)
        result["evidence"].append(entry)
        write_json(folder / "evidence" / "manifest.json", result)
    append_event(ctx, case_id, "evidence", caption if file else "截图未采集：" + (error or "缺少实际界面"),
                 evidence_id=evidence_id, basis_step=step_id, capture_status=entry["status"])
    return entry


def capture(ctx, case_id, step_id, name, caption, kind="browser", url=None, window_title=None, selector=None, timeout=30):
    folder = ctx.case_dir(case_id)
    ctx.case(case_id)
    capabilities = probe()
    write_json(folder / "evidence" / "capabilities.json", capabilities)
    temporary = folder / "evidence" / "capture-work" / (uuid.uuid4().hex[:8] + "-" + readable_name(name) + ".png")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    source = url if kind == "browser" else window_title
    operation = {"kind": kind, "url": url, "window_title": window_title, "selector": selector}
    try:
        if kind == "browser":
            if not url or not url.startswith(("http://", "https://")):
                raise ValueError("Browser evidence requires the actual HTTP(S) page URL")
            if not capabilities["browser"]["available"]:
                raise RuntimeError("No runnable local Playwright browser found; use an available host screenshot tool or manual import")
            from playwright.sync_api import sync_playwright
            failures = []
            for executable in capabilities["browser"]["executables"]:
                try:
                    with sync_playwright() as runtime:
                        browser = runtime.chromium.launch(headless=True, executable_path=executable)
                        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
                        page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
                        if selector:
                            page.locator(selector).screenshot(path=str(temporary), timeout=timeout * 1000)
                        else:
                            page.screenshot(path=str(temporary), full_page=True, timeout=timeout * 1000)
                        operation.update(executable=executable, actual_url=page.url, title=page.title(), provider="Playwright page.screenshot")
                        browser.close()
                    break
                except Exception as error:
                    failures.append(str(error)[:500])
            else:
                raise RuntimeError("Actual browser capture failed: " + " | ".join(failures))
        else:
            if not capabilities["desktop"]["available"] or not window_title:
                raise RuntimeError("Desktop/terminal capture requires a real visible window title and native capture support")
            import ctypes
            from ctypes import wintypes
            from PIL import ImageGrab
            user32 = ctypes.windll.user32
            matches = []
            callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            @callback_type
            def enumerate_window(handle, _):
                buffer = ctypes.create_unicode_buffer(1024)
                user32.GetWindowTextW(handle, buffer, 1024)
                if window_title.casefold() in buffer.value.casefold() and user32.IsWindowVisible(handle) and not user32.IsIconic(handle):
                    rectangle = wintypes.RECT()
                    user32.GetWindowRect(handle, ctypes.byref(rectangle))
                    if rectangle.right - rectangle.left > 10 and rectangle.bottom - rectangle.top > 10:
                        matches.append((handle, buffer.value, (rectangle.left, rectangle.top, rectangle.right, rectangle.bottom)))
                return True

            user32.EnumWindows(enumerate_window, 0)
            if len(matches) != 1:
                raise RuntimeError(f"Window title must match exactly one visible non-minimized window; matches={len(matches)}")
            handle, title, rectangle = matches[0]
            user32.SetForegroundWindow(handle)
            time.sleep(0.35)
            ImageGrab.grab(bbox=rectangle, all_screens=True).save(temporary)
            operation.update(actual_window_title=title, rectangle=rectangle, provider="Pillow ImageGrab native screen pixels")
        return add(ctx, case_id, step_id, kind, source, operation, caption, temporary, capture_verified=True)
    except Exception as error:
        return add(ctx, case_id, step_id, kind, source, operation, caption, error=str(error))
    finally:
        temporary.unlink(missing_ok=True)


def terminal_run(ctx, case_id, command, cwd, name, caption, timeout=60):
    """Run the real command in a real Windows console, capture it, close our process."""
    if os.name != "nt" or not command or not 1 <= timeout <= 300:
        raise ValueError("terminal-run requires Windows, explicit argv and a 1-300 second timeout")
    folder = ctx.case_dir(case_id)
    ctx.case(case_id)
    run_id = "run-" + uuid.uuid4().hex[:12]
    log_dir = folder / "runs" / run_id
    log_dir.mkdir(parents=True)
    title = "StyleForge-Evidence-" + uuid.uuid4().hex[:12]
    stdout_file = log_dir / "console-original.txt"
    exit_file = log_dir / "exit-code.txt"

    def ps_quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    actual_command = "& " + " ".join(ps_quote(part) for part in command)
    script = (
        "$ErrorActionPreference='Continue'; $env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'; "
        "$OutputEncoding=[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding; "
        f"$Host.UI.RawUI.WindowTitle={ps_quote(title)}; "
        f"Set-Location -LiteralPath {ps_quote(Path(cwd).resolve(strict=True))}; "
        f"{actual_command} 2>&1 | Tee-Object -FilePath {ps_quote(stdout_file)}; "
        "$sfExit=$LASTEXITCODE; if($null -eq $sfExit){$sfExit=0}; "
        f"[IO.File]::WriteAllText({ps_quote(exit_file)},[string]$sfExit)"
    )
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    conhost = shutil.which("conhost.exe")
    powershell = shutil.which("powershell.exe")
    if not conhost or not powershell:
        raise ValueError("Native console host and PowerShell are required; use another real capture route")
    launched_at = now()
    process = subprocess.Popen([conhost, powershell, "-NoLogo", "-NoProfile", "-NoExit", "-EncodedCommand", encoded])
    try:
        deadline = time.monotonic() + timeout
        while not exit_file.exists() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(0.2)
        timed_out = not exit_file.exists()
        raw = stdout_file.read_bytes() if stdout_file.exists() else b""
        decoded = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig", errors="replace")
        (log_dir / "stdout.bin").write_bytes(raw)
        (log_dir / "stdout.txt").write_text(decoded, encoding="utf-8")
        (log_dir / "stderr.bin").write_bytes(b"")
        (log_dir / "stderr.txt").write_text("", encoding="utf-8")
        report = {"run_id": run_id, "command": command, "cwd": str(Path(cwd).resolve()), "started_at": launched_at, "finished_at": now(),
                  "exit_code": int(exit_file.read_text().strip()) if exit_file.exists() else None, "timed_out": timed_out,
                  "stdout": (log_dir / "stdout.txt").relative_to(folder).as_posix(), "stderr": (log_dir / "stderr.txt").relative_to(folder).as_posix(),
                  "stdout_sha256": file_hash(log_dir / "stdout.bin"), "stderr_sha256": file_hash(log_dir / "stderr.bin"),
                  "provider": "real Windows conhost + PowerShell; Tee-Object preserves actual command output", "window_title": title,
                  "result_matches": [], "result_scope": "actual console output; challenge-specific checks still required"}
        write_json(log_dir / "run.json", report)
        event = append_event(ctx, case_id, "run", "在真实终端运行并采集关键画面。", **report, output_excerpt=decoded[:6000])
        if timed_out:
            image = add(ctx, case_id, event["id"], "terminal", title, {"command": command}, caption, error="Actual terminal run did not finish before timeout")
        else:
            image = capture(ctx, case_id, event["id"], name, caption, "terminal", window_title=title)
        return {"run": report, "step_id": event["id"], "evidence": image}
    finally:
        if process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)


def import_evidence(ctx, case_id, step_id, file, source, caption, host_receipt=None):
    verified = False
    operation = {"kind": "manual_import", "original_file": str(Path(file).resolve())}
    source_type = "user_supplied"
    if host_receipt:
        receipt = read_json(host_receipt)
        if receipt.get("file_sha256") != file_hash(file) or not receipt.get("tool_name") or not receipt.get("tool_call_ref"):
            raise ValueError("Host capture receipt must match the actual screenshot and tool call")
        # This is a recorded host attestation, not a cryptographic proof of pixels.
        operation.update(host_capture_receipt=receipt)
        source_type = "host_tool"
        verified = True
    return add(ctx, case_id, step_id, source_type, source, operation, caption, file, capture_verified=verified)


def confirm(ctx, case_id, evidence_id, receipt_path):
    receipt = read_json(receipt_path)
    folder = ctx.case_dir(case_id)
    with lock(folder / "evidence"):
        result = manifest(ctx, case_id)
        entry = next((item for item in result["evidence"] if item["id"] == evidence_id), None)
        if not entry or entry["status"] != "captured":
            raise ValueError("Captured evidence was not found")
        if receipt.get("owner_user") != ctx.user or receipt.get("file_sha256") != entry["sha256"] or receipt.get("decision") != "approved" or not receipt.get("confirmation_ref"):
            raise ValueError("User evidence confirmation is incomplete or mismatched")
        if bool(receipt.get("test_fixture", False)) != ctx.test:
            raise ValueError("Fixture confirmations must remain in fixture stores")
        entry.update(confirmed_by_user=True, confirmation_ref=receipt["confirmation_ref"])
        write_json(folder / "evidence" / "manifest.json", result)
    return entry
