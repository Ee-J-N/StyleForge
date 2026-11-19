#!/usr/bin/env python3
"""Executable helpers for StyleForge. Prose and reasoning remain the host Agent's work."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import casebook
import evidence_capture
import publishing
import style_profiles
from sf_core import Context, VERSION, copy_original, file_hash, load_events, now, read_json, write_json


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version="StyleForge " + VERSION)
    parser.add_argument("--store", help="Owner-isolated data root; default: D:/AI/codex/StyleForgeData on Windows")
    parser.add_argument("--user", help="Data owner ID, independent of sample author ID")
    parser.add_argument("--test-store", action="store_true", help="Create/use a clearly marked synthetic-fixture store")
    sub = parser.add_subparsers(dest="action", required=True)

    def command(name, help_text, profile=False, case=False):
        target = sub.add_parser(name, help=help_text)
        if profile:
            target.add_argument("--profile", required=True)
        if case:
            target.add_argument("--case", required=True)
        return target

    target = command("profile-learn", "Import one declared author's samples and measure their style", profile=True)
    target.add_argument("--author", required=True)
    target.add_argument("--sample", action="append", required=True, help="File or explicitly selected directory; repeatable")
    target.add_argument("--kind", choices=["historical_user", "external_author", "user_designated", "fixture"], default="user_designated")
    target.add_argument("--note", default="")
    target.add_argument("--update", action="store_true")
    command("profile-list", "List only the current owner's profiles")
    command("profile-show", "Read a profile, sample provenance, measurements and preferences", profile=True)
    target = command("profile-edit", "Edit preferences or add Agent qualitative analysis with sample IDs", profile=True)
    target.add_argument("--patch", required=True, help="JSON with preferences and/or qualitative_analysis")
    target = command("profile-export", "Export JSON or a ZIP with optional original samples", profile=True)
    target.add_argument("--output", required=True)
    target.add_argument("--include-samples", action="store_true")
    command("profile-delete", "Move a profile and its samples to owner-isolated trash", profile=True)
    target = command("profile-restore", "Undo a reversible profile deletion")
    target.add_argument("--token", required=True)
    target = command("profile-feedback", "Apply user-confirmed edits and explicitly update preferences", profile=True)
    target.add_argument("--before", required=True)
    target.add_argument("--edited", required=True)
    target.add_argument("--receipt", required=True)
    target.add_argument("--patch", help="JSON preference object; no automatic guess is treated as user preference")

    target = command("case-init", "Create independently selected style and recording dimensions", case=True)
    target.add_argument("--title", required=True)
    target.add_argument("--category", choices=["Web", "Crypto", "Reverse", "Pwn", "Misc", "Forensics", "Mixed"], required=True)
    target.add_argument("--profile")
    target.add_argument("--style-mode", choices=["learn", "write"], default="write")
    target.add_argument("--record-mode", choices=["solve", "replay"], default="replay")
    target.add_argument("--input", action="append", default=[])
    target = command("case-switch", "Change either dimension or selected profile without rewriting evidence", case=True)
    target.add_argument("--style-mode", choices=["learn", "write"])
    target.add_argument("--record-mode", choices=["solve", "replay"])
    target.add_argument("--profile")
    command("case-status", "Read the case, original events and evidence manifest", case=True)
    target = command("record", "Append a grounded observation, inference or historical source", case=True)
    target.add_argument("--kind", choices=["observation", "judgement", "payload", "source_analysis", "result", "note"], required=True)
    text = target.add_mutually_exclusive_group(required=True)
    text.add_argument("--text")
    text.add_argument("--text-file")
    target.add_argument("--basis")
    target.add_argument("--artifact")
    target.add_argument("--historical", action="store_true")
    target = command("run", "Execute explicit argv and preserve actual stdout/stderr/exit status", case=True)
    target.add_argument("--cwd")
    target.add_argument("--timeout", type=int, default=60)
    target.add_argument("--text", default="运行并记录实际命令。")
    target.add_argument("--result-pattern")
    target.add_argument("--script")
    target.add_argument("argv", nargs=argparse.REMAINDER)
    target = command("exp-check", "Inspect final EXP and optionally execute it in its actual environment", case=True)
    target.add_argument("--file", required=True)
    target.add_argument("--run", action="store_true")
    target.add_argument("--cwd")
    target.add_argument("--timeout", type=int, default=60)
    target.add_argument("--result-pattern")
    target.add_argument("--exp-arg", action="append", default=[], help="Argument passed to the selected EXP, not an alternate command")

    target = command("probe", "Check actual screenshot backends and optional host tool inventory")
    target.add_argument("--host-tools", help="JSON list of tool names obtained from the current host")
    target = command("capture", "Capture the actual page or visible native window", case=True)
    target.add_argument("--step", required=True)
    target.add_argument("--name", required=True)
    target.add_argument("--caption", required=True)
    target.add_argument("--kind", choices=["browser", "desktop", "terminal", "burp", "wireshark"], default="browser")
    target.add_argument("--url")
    target.add_argument("--window-title")
    target.add_argument("--selector")
    target.add_argument("--timeout", type=int, default=30)
    target = command("terminal-run", "Run in a real Windows console, capture actual pixels and close only that console", case=True)
    target.add_argument("--cwd", required=True)
    target.add_argument("--name", required=True)
    target.add_argument("--caption", required=True)
    target.add_argument("--timeout", type=int, default=60)
    target.add_argument("argv", nargs=argparse.REMAINDER)
    target = command("evidence-import", "Preserve a real user/host screenshot without redrawing it", case=True)
    target.add_argument("--step", required=True)
    target.add_argument("--file", required=True)
    target.add_argument("--source", required=True)
    target.add_argument("--caption", required=True)
    target.add_argument("--host-receipt")
    target = command("evidence-confirm", "Record the user's explicit confirmation of a screenshot", case=True)
    target.add_argument("--evidence", required=True)
    target.add_argument("--receipt", required=True)

    target = command("prepare", "Build an author-scoped writing packet for the host Agent", case=True)
    target.add_argument("--profile")
    target.add_argument("--references", type=int, default=3)
    target = command("publish", "Bind grounded Agent prose to evidence and validate a Markdown bundle", case=True)
    target.add_argument("--source", required=True)
    target.add_argument("--profile")
    target.add_argument("--attachment", action="append", default=[])
    target = command("check", "Check evidence, relative image links, results and measured style", case=True)
    target.add_argument("--article", required=True)
    target.add_argument("--profile")
    target = command("approve", "Archive exactly the revision confirmed by the actual user", case=True)
    target.add_argument("--article", required=True)
    target.add_argument("--receipt", required=True)
    target = sub.add_parser("bundle-check", help="Verify a self-contained candidate or approved publication archive")
    target.add_argument("--path", required=True)
    target = command("general-import", "Import general CTF reference material separately from personal style samples")
    target.add_argument("--input", required=True)
    target.add_argument("--note", required=True)
    return parser.parse_args()


def dispatch(ctx, args):
    action = args.action
    if action == "profile-learn":
        return style_profiles.learn(ctx, args.profile, args.author, args.sample, args.kind, args.note, args.update)
    if action == "profile-list":
        return [{key: profile[key] for key in ("id", "author_id", "owner_user", "version", "measurements")} for profile in
                (ctx.profile(path.parent.name) for path in sorted((ctx.owner / "profiles").glob("*/profile.json")))]
    if action == "profile-show":
        return ctx.profile(args.profile)
    if action == "profile-edit":
        return style_profiles.edit(ctx, args.profile, read_json(args.patch))
    if action == "profile-export":
        return style_profiles.export_profile(ctx, args.profile, args.output, args.include_samples)
    if action == "profile-delete":
        return style_profiles.delete_profile(ctx, args.profile)
    if action == "profile-restore":
        return style_profiles.restore_profile(ctx, args.token)
    if action == "profile-feedback":
        return style_profiles.feedback(ctx, args.profile, args.before, args.edited, args.receipt, read_json(args.patch) if args.patch else None)
    if action == "case-init":
        return casebook.init_case(ctx, args.case, args.title, args.category, args.profile, args.style_mode, args.record_mode, args.input)
    if action == "case-switch":
        return casebook.switch(ctx, args.case, args.style_mode, args.record_mode, args.profile)
    if action == "case-status":
        return {"case": ctx.case(args.case), "events": load_events(ctx.case_dir(args.case)), "evidence": evidence_capture.manifest(ctx, args.case)}
    if action == "record":
        text = Path(args.text_file).read_text(encoding="utf-8") if args.text_file else args.text
        return casebook.record(ctx, args.case, args.kind, text, args.basis, args.artifact, args.historical)
    if action in ("run", "exp-check"):
        if action == "run":
            argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
            return casebook.run(ctx, args.case, argv, args.cwd, args.timeout, args.text, args.result_pattern, args.script)
        return casebook.exp_check(ctx, args.case, args.file, args.run, args.cwd, args.timeout,
                                  args.result_pattern, args.exp_arg)
    if action == "probe":
        return evidence_capture.probe(read_json(args.host_tools) if args.host_tools else ())
    if action == "capture":
        return evidence_capture.capture(ctx, args.case, args.step, args.name, args.caption, args.kind, args.url, args.window_title, args.selector, args.timeout)
    if action == "terminal-run":
        argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
        return evidence_capture.terminal_run(ctx, args.case, argv, args.cwd, args.name, args.caption, args.timeout)
    if action == "evidence-import":
        return evidence_capture.import_evidence(ctx, args.case, args.step, args.file, args.source, args.caption, args.host_receipt)
    if action == "evidence-confirm":
        return evidence_capture.confirm(ctx, args.case, args.evidence, args.receipt)
    if action == "prepare":
        return publishing.prepare(ctx, args.case, args.profile, args.references)
    if action == "publish":
        return publishing.publish(ctx, args.case, args.source, args.profile, args.attachment)
    if action == "check":
        path = Path(args.article).parent / "evidence" / "manifest.json"
        return publishing.check_document(ctx, args.case, args.article, args.profile, read_json(path) if path.exists() else None)
    if action == "approve":
        return publishing.approve(ctx, args.case, args.article, args.receipt)
    if action == "bundle-check":
        return publishing.verify_bundle(args.path)
    if action == "general-import":
        checksum = file_hash(args.input)
        destination = copy_original(args.input, ctx.root / "general" / checksum[:16])
        entry = {"path": str(destination), "source": str(Path(args.input).resolve()), "sha256": checksum, "note": args.note, "imported_at": now(),
                 "classification": "general-reference; excluded from personal style selection"}
        write_json(destination.parent / "reference.json", entry)
        return entry
    raise ValueError("Unknown command")


def main():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")
    args = arguments()
    try:
        ctx = None if args.action == "bundle-check" else Context(args.store, args.user, args.test_store)
        result = dispatch(ctx, args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if isinstance(result, dict) and (result.get("passed") is False or result.get("status") in
                                          ("unavailable", "validation_failed", "failed", "timed_out", "unverified")):
            return 2
        return 0
    except Exception as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
