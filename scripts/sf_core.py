"""Local, owner-scoped persistence for the StyleForge Agent Skill."""

from __future__ import annotations

import contextlib
import datetime as dt
import getpass
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

VERSION = "1.0.1"
SCHEMA = 1


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def identifier(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
        raise ValueError("Identifiers must use 1-80 letters, digits, underscores or hyphens")
    return value


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    with Path(path).open("rb") as stream:
        result = hashlib.file_digest(stream, "sha256")
    return result.hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, value):
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def child(root, *parts):
    root = Path(root).resolve()
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path escapes its data boundary: {path}")
    return path


def readable_name(value):
    value = re.sub(r"[^\w.\-]+", "-", str(value), flags=re.UNICODE).strip(".-") or "artifact"
    if len(value) > 100:
        suffix = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        value = value[:83].rstrip(".-") + "-" + suffix
    return value


def copy_original(source, folder, prefix=""):
    source = Path(source).resolve(strict=True)
    if not source.is_file():
        raise ValueError(f"Expected a file: {source}")
    target = child(folder, prefix + readable_name(source.name))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if file_hash(source) != file_hash(target):
            raise ValueError(f"Preserved original already exists with different bytes: {target}")
    else:
        shutil.copy2(source, target)
    return target


@contextlib.contextmanager
def lock(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ".styleforge.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError(f"Data is in use; retry after the active operation finishes: {path}") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.close(descriptor)
        yield
    finally:
        path.unlink(missing_ok=True)


def default_store_path():
    configured = os.environ.get("STYLEFORGE_DATA_HOME")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        return Path("D:/AI/codex/StyleForgeData")
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "StyleForge"


def default_browser_path():
    configured = os.environ.get("STYLEFORGE_BROWSERS_HOME")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        return Path("D:/AI/codex/StyleForgeData/playwright-browsers")
    return Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / ".cache/ms-playwright")))


class Context:
    def __init__(self, store=None, user=None, test_store=False):
        selected = Path(store).expanduser() if store else default_store_path()
        self.root = selected.expanduser().resolve()
        if os.name == "nt" and self.root.drive.casefold() != "d:":
            raise ValueError("StyleForge data must be stored on D:; use --store or STYLEFORGE_DATA_HOME with a D: path")
        browser_root = default_browser_path().resolve()
        if os.name == "nt" and browser_root.drive.casefold() != "d:":
            raise ValueError("Playwright browsers must be stored on D:; use STYLEFORGE_BROWSERS_HOME with a D: path")
        self.user = identifier(user or getpass.getuser())
        self.root.mkdir(parents=True, exist_ok=True)
        runtime_tmp = self.root / "runtime" / "tmp"
        runtime_tmp.mkdir(parents=True, exist_ok=True)
        os.environ["TEMP"] = str(runtime_tmp)
        os.environ["TMP"] = str(runtime_tmp)
        os.environ["TMPDIR"] = str(runtime_tmp)
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_root)
        tempfile.tempdir = str(runtime_tmp)
        marker = self.root / "store.json"
        if not marker.exists():
            write_json(marker, {"schema_version": SCHEMA, "created_at": now(), "test_fixture": bool(test_store)})
        self.test = read_json(marker).get("test_fixture", False)
        if test_store and not self.test:
            raise ValueError("A real data store must not be relabeled as a fixture store")
        self.owner = child(self.root, "users", self.user)
        self.owner.mkdir(parents=True, exist_ok=True)

    def profile_dir(self, name):
        return child(self.owner, "profiles", identifier(name))

    def case_dir(self, name):
        return child(self.owner, "cases", identifier(name))

    def profile(self, name):
        result = read_json(self.profile_dir(name) / "profile.json")
        if result["owner_user"] != self.user or result["id"] != name:
            raise ValueError("Profile ownership mismatch")
        for sample in result["samples"]:
            if sample["author_id"] != result["author_id"]:
                raise ValueError("Profile contains samples from a different author")
        return result

    def case(self, name):
        result = read_json(self.case_dir(name) / "case.json")
        if result["owner_user"] != self.user or result["id"] != name:
            raise ValueError("Case ownership mismatch")
        return result


def load_events(case_dir):
    path = Path(case_dir) / "events.jsonl"
    if not path.exists():
        return []
    result = []
    previous = "0" * 64
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        claimed = event.pop("event_sha256")
        if event["previous_sha256"] != previous or digest(canonical(event).encode("utf-8")) != claimed:
            raise ValueError("Event journal integrity check failed")
        event["event_sha256"] = claimed
        result.append(event)
        previous = claimed
    return result


def append_event(ctx, case_id, kind, text, **details):
    folder = ctx.case_dir(case_id)
    with lock(folder):
        case = ctx.case(case_id)
        events = load_events(folder)
        event = {
            "schema_version": SCHEMA,
            "id": "step-" + uuid.uuid4().hex[:12],
            "sequence": len(events) + 1,
            "timestamp": now(),
            "kind": kind,
            "text": text,
            "owner_user": ctx.user,
            "style_mode": case["style_mode"],
            "record_mode": case["record_mode"],
            "origin": "live_solve" if case["record_mode"] == "solve" else "replay_validation",
            "previous_sha256": events[-1]["event_sha256"] if events else "0" * 64,
        }
        event.update(details)
        event["event_sha256"] = digest(canonical(event).encode("utf-8"))
        with (folder / "events.jsonl").open("a", encoding="utf-8", newline="\n") as output:
            output.write(canonical(event) + "\n")
        draft = folder / "draft.md"
        if not draft.exists():
            write_text(draft, f"# {case['title']}\n\n解题过程草稿；事件标记保留对应的证据来源。\n")
        block = f"\n<!-- step:{event['id']} -->\n\n{text}\n"
        if event.get("command"):
            block += "\n实际命令参数（JSON 数组，按顺序执行）：\n\n```json\n" + json.dumps(event["command"], ensure_ascii=False) + "\n```\n"
        if event.get("output_excerpt"):
            block += "\n原始运行输出节选：\n\n```text\n" + event["output_excerpt"].rstrip() + "\n```\n"
        if event.get("evidence_id"):
            block += f"\n<!-- evidence:{event['evidence_id']} -->\n"
        with draft.open("a", encoding="utf-8", newline="\n") as output:
            output.write(block)
    return event


def validate_receipt(ctx, receipt_path, article):
    receipt = read_json(receipt_path)
    required = ("owner_user", "decision", "article_sha256", "confirmed_by", "confirmation_ref", "confirmed_at")
    if any(not receipt.get(key) for key in required):
        raise ValueError("Confirmation receipt is incomplete")
    if receipt["owner_user"] != ctx.user or receipt["decision"] != "approved":
        raise ValueError("Receipt owner or decision does not match")
    if receipt["article_sha256"] != file_hash(article):
        raise ValueError("Article changed after confirmation; obtain confirmation for the current bytes")
    if bool(receipt.get("test_fixture", False)) != ctx.test:
        raise ValueError("Fixture confirmations and real personal data stores must remain separate")
    if receipt["confirmed_by"] not in ("user", "fixture-user" if ctx.test else "user"):
        raise ValueError("Confirmation must identify the user, not the generating agent")
    return receipt
