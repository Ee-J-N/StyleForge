"""Isolated regression tests for the audited StyleForge P1/P2 findings."""

from __future__ import annotations

import hashlib
import json
import os
import http.server
import functools
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import casebook
import evidence_capture
import markdown_links
import publishing
import sf_core
import style_profiles


class StyleForgeAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="styleforge-fixture-")
        self.root = Path(self.temp.name)
        self.ctx = sf_core.Context(self.root / "store", "audit-user", True)
        self.fixture = self.root / "fixtures"
        self.fixture.mkdir()
        sample = self.write("style.md", "# Synthetic style\n\nInspect first, then test.\n")
        style_profiles.learn(self.ctx, "profile", "fixture-author", [sample], "fixture", "Audit fixture")

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, text):
        path = self.fixture / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def digest(self, path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def make_case(self, name="case", inputs=()):
        return casebook.init_case(self.ctx, name, "Fixture case", "Crypto", "profile", "write", "replay", inputs)

    def article(self, name="article", body="The replay was inspected."):
        return self.write(name + ".md", "# Fixture article\n\nReplay was checked locally.\n\n" + body + "\n")

    def run_cli(self, *args):
        command = [sys.executable, "-B", "-X", "utf8", str(ROOT / "scripts/styleforge.py"),
                   "--store", str(self.ctx.root), "--user", self.ctx.user, "--test-store", *map(str, args)]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        return subprocess.run(command, capture_output=True, timeout=15, env=env)

    def run_events(self, case_id):
        return [event for event in sf_core.load_events(self.ctx.case_dir(case_id)) if event["kind"] == "run"]

    def verified_fixture_exp(self, case_id="case", name="exp.py", source=None, expected=r"FLAG\{[A-Z]+\}"):
        source = source if source is not None else "print('FLAG{SYNTHETIC}')\n"
        path = self.write(name, source)
        self.make_case(case_id, [path])
        snap = self.ctx.case_dir(case_id) / "inputs" / "files" / name
        report = casebook.exp_check(self.ctx, case_id, snap, True, result_pattern=expected)
        return snap, report

    def receipt(self, article):
        path = self.write("receipt.json", json.dumps({
            "owner_user": self.ctx.user,
            "decision": "approved",
            "article_sha256": self.digest(article),
            "confirmed_by": "fixture-user",
            "confirmation_ref": "AUDIT-FIXTURE-ONLY",
            "confirmed_at": sf_core.now(),
            "test_fixture": True,
        }))
        return path

    def test_exp_execution_is_bound_to_the_exact_input_file(self):
        path, report = self.verified_fixture_exp()
        run = report["runtime"]
        self.assertEqual(report["status"], "passed")
        self.assertEqual(Path(run["script_path"]).resolve(), path.resolve())
        self.assertEqual(run["script_sha256"], self.digest(path))
        self.assertIn(str(path.resolve()), run["command"])

    def test_exp_without_result_check_is_not_marked_successful(self):
        path = self.write("no-check.py", "print('program ran')\n")
        self.make_case("no-check", [path])
        result = casebook.exp_check(self.ctx, "no-check", self.ctx.case_dir("no-check") / "inputs/files/no-check.py", True)
        self.assertEqual(result["runtime"]["exit_code"], 0)
        self.assertEqual(result["status"], "unverified")
        self.assertNotEqual(result["status"], "passed")

    def test_exp_check_rejects_an_alternate_command_line(self):
        self.make_case("alternate")
        process = self.run_cli("exp-check", "--case", "alternate", "--file", __file__, "--run",
                               "--result-pattern", r".*", "--", sys.executable, "-c", "print('different command')")
        self.assertNotEqual(process.returncode, 0)
        self.assertIn(b"unrecognized arguments", process.stderr)

    def test_cli_executes_the_selected_exp_and_reports_verified_result(self):
        source = self.write("cli-exp.py", "print('FLAG{SYNTHETIC}')\n")
        self.make_case("cli-exp", [source])
        selected = self.ctx.case_dir("cli-exp") / "inputs/files/cli-exp.py"
        process = self.run_cli("exp-check", "--case", "cli-exp", "--file", selected, "--run",
                               "--result-pattern", r"FLAG\{[A-Z]+\}")
        self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8", errors="replace"))
        self.assertEqual(json.loads(process.stdout)["status"], "passed")

    def test_cli_does_not_report_an_exp_without_result_check_as_success(self):
        source = self.write("cli-unverified.py", "print('program ran')\n")
        self.make_case("cli-unverified", [source])
        selected = self.ctx.case_dir("cli-unverified") / "inputs/files/cli-unverified.py"
        process = self.run_cli("exp-check", "--case", "cli-unverified", "--file", selected, "--run")
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(json.loads(process.stdout)["status"], "unverified")

    def test_exp_result_pattern_must_match_actual_output(self):
        path = self.write("unmatched.py", "print('not the expected result')\n")
        self.make_case("unmatched", [path])
        result = casebook.exp_check(self.ctx, "unmatched", self.ctx.case_dir("unmatched") / "inputs/files/unmatched.py",
                                    True, result_pattern=r"flag\{[a-z]+\}")
        self.assertEqual(result["status"], "validation_failed")
        self.assertEqual(result["runtime"]["result_validation"]["status"], "failed")

    def test_exp_content_change_invalidates_previously_verified_result(self):
        path, report = self.verified_fixture_exp("changed")
        path.write_text("print('changed-result')\n", encoding="utf-8")
        article = self.article("changed", "The result is FLAG{SYNTHETIC}.")
        checked = publishing.check_document(self.ctx, "changed", article)
        self.assertFalse(checked["passed"])
        self.assertTrue(any("Flag" in error for error in checked["errors"]))
        self.assertTrue(any("EXP file changed" in warning for warning in checked["warnings"]))
        self.assertEqual(report["status"], "passed")

    def test_unchecked_run_cannot_supply_a_flag(self):
        self.make_case("unchecked")
        casebook.run(self.ctx, "unchecked", [sys.executable, "-c", "print('FLAG{SYNTHETIC}')"])
        checked = publishing.check_document(self.ctx, "unchecked", self.article("unchecked", "FLAG{SYNTHETIC}"))
        self.assertFalse(checked["passed"])
        self.assertTrue(any("Flag" in error for error in checked["errors"]))

    def test_modified_derived_stdout_is_never_used_as_flag_evidence(self):
        self.make_case("stdout-tamper")
        run = casebook.run(self.ctx, "stdout-tamper", [sys.executable, "-c", "print('original')"])
        (self.ctx.case_dir("stdout-tamper") / run["stdout"]).write_text("FLAG{SYNTHETIC}\n", encoding="utf-8")
        checked = publishing.check_document(self.ctx, "stdout-tamper", self.article("stdout-tamper", "FLAG{SYNTHETIC}"))
        self.assertFalse(checked["passed"])
        self.assertTrue(any("Flag" in error for error in checked["errors"]))

    def test_missing_raw_stdout_invalidates_a_run_record(self):
        self.make_case("raw-missing")
        run = casebook.run(self.ctx, "raw-missing", [sys.executable, "-c", "print('original')"])
        (self.ctx.case_dir("raw-missing") / run["stdout"]).with_suffix(".bin").unlink()
        checked = publishing.check_document(self.ctx, "raw-missing", self.article("raw-missing"))
        self.assertFalse(checked["passed"])
        self.assertTrue(any("raw" in error.lower() or "stdout" in error.lower() for error in checked["errors"]))

    def test_cli_reports_nonzero_command_failure(self):
        self.make_case("failed-cli")
        process = self.run_cli("run", "--case", "failed-cli", "--", sys.executable, "-c", "raise SystemExit(7)")
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(json.loads(process.stdout)["exit_code"], 7)

    def test_cli_reports_command_timeout(self):
        self.make_case("timeout-cli")
        process = self.run_cli("run", "--case", "timeout-cli", "--timeout", "1", "--",
                               sys.executable, "-c", "import time; time.sleep(3)")
        self.assertNotEqual(process.returncode, 0)
        self.assertTrue(json.loads(process.stdout)["timed_out"])

    def test_publish_rejects_missing_inline_image(self):
        self.make_case("missing-image")
        checked = publishing.check_document(self.ctx, "missing-image",
                                             self.article("missing-image", "![missing](missing.png)"))
        self.assertFalse(checked["passed"])
        self.assertTrue(any("Missing image" in error for error in checked["errors"]))

    def test_published_image_bytes_must_match_the_case_capture(self):
        self.make_case("image-tamper")
        from PIL import Image
        screen = self.root / "screen.png"
        Image.new("RGB", (4, 4), "white").save(screen)
        step = casebook.record(self.ctx, "image-tamper", "observation", "fixture step")
        evidence = evidence_capture.add(self.ctx, "image-tamper", step["id"], "user_supplied", "fixture screenshot",
                                        {"kind": "fixture"}, "fixture screenshot", screen)
        article = self.article("image-tamper", "![screen](" + evidence["path"] + ")")
        candidate = publishing.publish(self.ctx, "image-tamper", article)
        target = Path(candidate["article"]).parent / evidence["path"]
        target.write_bytes(b"not the captured screenshot")
        checked = publishing.check_document(self.ctx, "image-tamper", Path(candidate["article"]))
        self.assertFalse(checked["passed"])
        self.assertTrue(any("screenshot bytes differ" in error for error in checked["errors"]))

    def test_publish_checks_reference_style_image(self):
        self.make_case("reference-image")
        checked = publishing.check_document(self.ctx, "reference-image", self.article(
            "reference-image", "![screen][capture]\n\n[capture]: missing-reference.png"))
        self.assertFalse(checked["passed"])
        self.assertTrue(any("missing-reference.png" in error for error in checked["errors"]))

    def test_markdown_escaped_punctuation_is_decoded_in_link_destination(self):
        links = markdown_links.extract_links(r"[source](files/exp\(draft\).py)")
        self.assertEqual(links, [{"kind": "link", "target": "files/exp(draft).py"}])

    def test_image_markup_inside_code_is_not_an_image_reference(self):
        self.make_case("fenced-image")
        checked = publishing.check_document(self.ctx, "fenced-image", self.article(
            "fenced-image", "```markdown\n![example](not-an-image.png)\n```"))
        self.assertTrue(checked["passed"], checked["errors"])

    def test_evidence_marker_examples_inside_code_are_not_replaced_or_rejected(self):
        self.make_case("marker-example")
        body = "```markdown\n<!-- evidence:example-id -->\n```\n\n`<!-- evidence:inline-example -->`"
        candidate = publishing.publish(self.ctx, "marker-example", self.article("marker-example", body))
        self.assertEqual(candidate["status"], "published_candidate", candidate["validation"])
        article = Path(candidate["article"]).read_text(encoding="utf-8")
        self.assertIn("<!-- evidence:example-id -->", article)
        self.assertIn("<!-- evidence:inline-example -->", article)

    def test_publish_rejects_missing_exp_hyperlink(self):
        self.make_case("missing-exp")
        checked = publishing.check_document(self.ctx, "missing-exp",
                                             self.article("missing-exp", "[EXP](files/missing-exp.py)"))
        self.assertFalse(checked["passed"])
        self.assertTrue(any("missing-exp.py" in error for error in checked["errors"]))

    def test_publish_rejects_malformed_external_links(self):
        self.make_case("bad-link")
        checked = publishing.check_document(self.ctx, "bad-link",
                                             self.article("bad-link", "[bad link](https://)"))
        self.assertFalse(checked["passed"])

    def test_local_link_with_an_omitted_file_is_rejected(self):
        self.make_case("local-link")
        checked = publishing.check_document(self.ctx, "local-link",
                                             self.article("local-link", "[source](missing.txt)"))
        self.assertFalse(checked["passed"])

    def test_image_must_be_bound_to_the_current_case(self):
        self.make_case("image-source")
        self.make_case("image-destination")
        path = self.write("pixel.png", "")
        from PIL import Image
        Image.new("RGB", (4, 4), "white").save(path)
        step = casebook.record(self.ctx, "image-source", "observation", "fixture step")
        evidence = evidence_capture.add(self.ctx, "image-source", step["id"], "user_supplied", "fixture screenshot",
                                        {"kind": "fixture"}, "fixture screenshot", path)
        source = self.ctx.case_dir("image-destination") / "outputs" / "writeup.md"
        source.parent.mkdir(parents=True)
        source.write_text("# Fixture\n\n![screen](" + evidence["path"] + ")\n", encoding="utf-8")
        foreign_manifest = {"owner_user": self.ctx.user, "case_id": "image-source", "evidence": [evidence]}
        checked = publishing.check_document(self.ctx, "image-destination", source, evidence_manifest=foreign_manifest)
        self.assertFalse(checked["passed"])
        self.assertTrue(any("case" in error.lower() for error in checked["errors"]))

    def test_publish_bundle_preserves_all_case_inputs_and_runtime_records(self):
        exp = self.write("attachment.py", "print('FLAG{SYNTHETIC}')\n")
        self.make_case("bundle", [exp])
        exp_snapshot = self.ctx.case_dir("bundle") / "inputs/files/attachment.py"
        result = casebook.exp_check(self.ctx, "bundle", exp_snapshot, True, result_pattern=r"FLAG\{[A-Z]+\}")
        self.assertEqual(result["status"], "passed")
        article = self.article("bundle", "[EXP](files/attachment.py)")
        candidate = publishing.publish(self.ctx, "bundle", article, attachments=[exp])
        self.assertEqual(candidate["status"], "published_candidate")
        bundle = Path(candidate["article"]).parent
        self.assertEqual(self.digest(bundle / "files/attachment.py"), self.digest(exp))
        self.assertTrue((bundle / "provenance/events.jsonl").is_file())
        self.assertTrue((bundle / "provenance/inputs/files/attachment.py").is_file())
        runs = list((bundle / "provenance/runs").glob("*/run.json"))
        self.assertEqual(len(runs), 1)
        self.assertTrue(list((bundle / "provenance/runs").glob("*/inputs/attachment.py")))

    def test_exp_links_are_checked_and_copied_into_candidate_bundle(self):
        exp = self.write("working.py", "print('FLAG{SYNTHETIC}')\n")
        self.make_case("linked-exp", [exp])
        candidate = publishing.publish(self.ctx, "linked-exp", self.article(
            "linked-exp", "[EXP](files/working.py)"), attachments=[exp])
        self.assertEqual(candidate["status"], "published_candidate", candidate["validation"])
        checked = candidate["validation"]
        self.assertTrue(checked["passed"])

    def test_approved_archive_preserves_attachments_and_images(self):
        self.make_case("approved")
        attachment = self.write("solver.py", "print('fixture')\n")
        from PIL import Image
        screen = self.root / "screen.png"
        Image.new("RGB", (4, 4), "white").save(screen)
        step = casebook.record(self.ctx, "approved", "observation", "fixture step")
        evidence = evidence_capture.add(self.ctx, "approved", step["id"], "user_supplied", "fixture screenshot",
                                        {"kind": "fixture"}, "fixture screenshot", screen)
        source = self.article("approved", "![screen](" + evidence["path"] + ")\n\n[EXP](files/solver.py)")
        candidate = publishing.publish(self.ctx, "approved", source, attachments=[attachment])
        self.assertEqual(candidate["status"], "published_candidate")
        article = Path(candidate["article"])
        approved = publishing.approve(self.ctx, "approved", article, self.receipt(article))
        archive = Path(approved["approved_article"]).parent
        self.assertEqual(self.digest(archive / "files/solver.py"), self.digest(attachment))
        self.assertTrue((archive / evidence["path"]).is_file())
        self.assertTrue((archive / "evidence/manifest.json").is_file())
        self.assertTrue((archive / "confirmation.json").is_file())

    def test_historical_results_are_archived_and_labelled_as_history(self):
        self.make_case("history")
        source = self.write("history.txt", "Previously solved: FLAG{SYNTHETIC_HISTORY}\n")
        casebook.record(self.ctx, "history", "result", "User supplied historical result", artifact=source, historical=True)
        candidate = publishing.publish(self.ctx, "history", self.article(
            "history", "The imported historical result was not re-executed: FLAG{SYNTHETIC_HISTORY}."))
        self.assertEqual(candidate["status"], "published_candidate", candidate["validation"])
        archive = Path(candidate["article"]).parent
        self.assertTrue(list((archive / "provenance/history").glob("*.txt")))
        self.assertTrue((archive / "provenance/events.jsonl").is_file())

    def test_article_without_user_approval_remains_a_candidate(self):
        self.make_case("approval-gate")
        candidate = publishing.publish(self.ctx, "approval-gate", self.article("approval-gate"))
        self.assertEqual(candidate["status"], "published_candidate")
        revision = self.ctx.case("approval-gate")["revisions"][-1]
        self.assertFalse(revision["approved"])
        self.assertFalse((self.ctx.owner / "approved").exists())

    def test_candidate_bundle_can_be_reverified_without_case_context(self):
        exp = self.write("standalone.py", "print('FLAG{SYNTHETIC}')\n")
        self.make_case("standalone", [exp])
        snap = self.ctx.case_dir("standalone") / "inputs/files/standalone.py"
        casebook.exp_check(self.ctx, "standalone", snap, True, result_pattern=r"FLAG\{[A-Z]+\}")
        candidate = publishing.publish(self.ctx, "standalone", self.article("standalone"))
        result = publishing.verify_bundle(candidate["bundle"])
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["status"], "candidate")
        process = self.run_cli("bundle-check", "--path", candidate["bundle"])
        self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8", errors="replace"))
        self.assertTrue(json.loads(process.stdout)["passed"])

    def test_bundle_reverification_does_not_require_the_original_interpreter(self):
        exp = self.write("portable.py", "print('FLAG{SYNTHETIC}')\n")
        self.make_case("portable", [exp])
        snap = self.ctx.case_dir("portable") / "inputs/files/portable.py"
        casebook.exp_check(self.ctx, "portable", snap, True, result_pattern=r"FLAG\{[A-Z]+\}")
        article = self.article("portable")
        with patch.object(casebook, "_script_runtime", side_effect=AssertionError("interpreter discovery")):
            checked = publishing.check_document(self.ctx, "portable", article)
            self.assertTrue(checked["passed"], checked["errors"])
            candidate = publishing.publish(self.ctx, "portable", article)
            result = publishing.verify_bundle(candidate["bundle"])
        self.assertTrue(result["passed"], result["errors"])

    def test_bundle_check_detects_modified_archived_runtime_bytes(self):
        exp = self.write("tamper.py", "print('FLAG{SYNTHETIC}')\n")
        self.make_case("bundle-tamper", [exp])
        snap = self.ctx.case_dir("bundle-tamper") / "inputs/files/tamper.py"
        casebook.exp_check(self.ctx, "bundle-tamper", snap, True, result_pattern=r"FLAG\{[A-Z]+\}")
        candidate = publishing.publish(self.ctx, "bundle-tamper", self.article("bundle-tamper"))
        log = next(Path(candidate["bundle"]).glob("provenance/runs/*/stdout.bin"))
        log.write_bytes(b"FLAG{MODIFIED}\n")
        result = publishing.verify_bundle(candidate["bundle"])
        self.assertFalse(result["passed"])
        self.assertTrue(any("hash mismatch" in error for error in result["errors"]))

    def test_user_edit_is_rechecked_before_exact_revision_approval(self):
        self.make_case("edited-candidate")
        candidate = publishing.publish(self.ctx, "edited-candidate", self.article("edited-candidate"))
        article = Path(candidate["article"])
        article.write_text("# Fixture article\n\nEdited after the candidate was created.\n", encoding="utf-8")
        approved = publishing.approve(self.ctx, "edited-candidate", article, self.receipt(article))
        result = publishing.verify_bundle(Path(approved["approved_article"]).parent)
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["status"], "approved")

    def test_unlisted_candidate_file_is_not_promoted_to_approved_bundle(self):
        self.make_case("unlisted")
        candidate = publishing.publish(self.ctx, "unlisted", self.article("unlisted"))
        article = Path(candidate["article"])
        (article.parent / "extra.py").write_text("print('unreviewed')\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            publishing.approve(self.ctx, "unlisted", article, self.receipt(article))
        self.assertFalse((self.ctx.owner / "approved").exists())

    def test_external_links_are_not_fetched_during_validation(self):
        self.make_case("external-link")
        checked = publishing.check_document(self.ctx, "external-link",
                                             self.article("external-link", "[example](https://example.com/path)"))
        self.assertTrue(checked["passed"], checked["errors"])
        self.assertTrue(any("not fetched" in warning for warning in checked["warnings"]))

    def test_profile_names_that_truncate_to_same_prefix_remain_distinct(self):
        first = "a" * 110 + "first.md"
        second = "a" * 110 + "second.md"
        self.assertLessEqual(len(sf_core.readable_name(first)), 100)
        self.assertLessEqual(len(sf_core.readable_name(second)), 100)
        self.assertNotEqual(sf_core.readable_name(first), sf_core.readable_name(second))

    def test_local_browser_capture_records_real_pixels_and_reverifies(self):
        capabilities = evidence_capture.probe()
        if not capabilities["browser"]["available"]:
            self.skipTest("Playwright Chromium is unavailable on this machine")
        webroot = self.root / "web"
        webroot.mkdir()
        (webroot / "index.html").write_text(
            "<!doctype html><meta charset='utf-8'><title>StyleForge audit fixture</title>"
            "<h1>Local screenshot fixture</h1><p>Synthetic test page, not a challenge target.</p>", encoding="utf-8")

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(webroot)))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            self.make_case("browser-capture")
            step = casebook.record(self.ctx, "browser-capture", "observation", "Loaded the local fixture page")
            evidence = evidence_capture.capture(self.ctx, "browser-capture", step["id"], "local-fixture",
                                                "Local synthetic browser page", url=f"http://127.0.0.1:{server.server_port}/")
            self.assertEqual(evidence["status"], "captured", evidence)
            self.assertTrue(evidence["capture_verified"])
            source = self.article("browser-capture", "<!-- evidence:" + evidence["id"] + " -->")
            candidate = publishing.publish(self.ctx, "browser-capture", source)
            self.assertEqual(candidate["status"], "published_candidate", candidate["validation"])
            bundle = publishing.verify_bundle(candidate["bundle"])
            self.assertTrue(bundle["passed"], bundle["errors"])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)

    def test_case_initialization_failure_rolls_back_and_retry_succeeds(self):
        first = self.write("one.txt", "first\n")
        with self.assertRaises(FileNotFoundError):
            casebook.init_case(self.ctx, "retry", "Fixture", "Misc", inputs=[first, self.fixture / "missing.txt"])
        self.assertFalse(self.ctx.case_dir("retry").exists())
        casebook.init_case(self.ctx, "retry", "Fixture", "Misc", inputs=[first])
        self.assertTrue((self.ctx.case_dir("retry") / "case.json").is_file())

    def test_case_initialization_duplicate_input_collision_rolls_back(self):
        first = self.write("left/same.txt", "one\n")
        second = self.write("right/same.txt", "two\n")
        with self.assertRaises(ValueError):
            casebook.init_case(self.ctx, "collision", "Fixture", "Misc", inputs=[first, second])
        self.assertFalse(self.ctx.case_dir("collision").exists())

    def test_case_init_never_overwrites_an_existing_case(self):
        self.make_case("preserve")
        original = (self.ctx.case_dir("preserve") / "case.json").read_bytes()
        incoming = self.write("new-input.txt", "new input\n")
        with self.assertRaises(ValueError):
            self.make_case("preserve", [incoming])
        self.assertEqual((self.ctx.case_dir("preserve") / "case.json").read_bytes(), original)
        self.assertEqual(list((self.ctx.case_dir("preserve")).glob(".init-*")), [])

    def test_profile_batch_import_failure_leaves_no_partial_samples(self):
        original = self.ctx.profile("profile")
        good = self.write("good.md", "# Additional sample\n\nThis sample parses correctly.\n")
        bad = self.fixture / "bad.md"
        bad.write_bytes(b"\xff")
        with self.assertRaisesRegex(ValueError, "Unrecognized text encoding"):
            style_profiles.learn(self.ctx, "profile", "fixture-author", [good, bad], "fixture", update=True)
        current = self.ctx.profile("profile")
        self.assertEqual(current["version"], original["version"])
        self.assertEqual(len(current["samples"]), len(original["samples"]))
        self.assertEqual(len(list((self.ctx.profile_dir("profile") / "samples").glob(".learn-*"))), 0)
        self.assertEqual(len(list((self.ctx.profile_dir("profile") / "samples").glob("sample-*"))), 1)

    def test_skill_entry_is_a_loadable_non_scaffold_instruction(self):
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---\n"))
        frontmatter = content.split("---\n", 2)[1]
        self.assertIn("name: styleforge", frontmatter)
        self.assertIn("description:", frontmatter)
        self.assertNotIn("TODO", frontmatter + content.split("---\n", 2)[2])
        for mode in ("Learn Mode", "Write Mode", "Solve & Write", "Replay & Write"):
            self.assertIn(mode, content)
        for reference in ("INSTALL.md", "README.md", "DEVELOPMENT.md"):
            self.assertTrue((ROOT / reference).is_file())

    def test_profile_export_does_not_overwrite_an_existing_file(self):
        destination = self.write("existing-profile.json", "preserve original export target\n")
        original = destination.read_bytes()
        with self.assertRaises(ValueError):
            style_profiles.export_profile(self.ctx, "profile", destination)
        self.assertEqual(destination.read_bytes(), original)

    def test_maximum_length_profile_name_can_be_restored(self):
        name = "p" * 80
        sample = self.write("long-style.md", "# Style\n\nLong profile fixture.\n")
        style_profiles.learn(self.ctx, name, "fixture-author", [sample], "fixture")
        deleted = style_profiles.delete_profile(self.ctx, name)
        restored = style_profiles.restore_profile(self.ctx, deleted["restore_token"])
        self.assertEqual(restored["restored"], name)

    def test_overlong_restore_token_is_rejected_before_mutation(self):
        with self.assertRaises(ValueError):
            style_profiles.restore_profile(self.ctx, "x" * 81)
        self.assertEqual(len(list((self.ctx.owner / "trash/profiles").glob("*"))) if (self.ctx.owner / "trash/profiles").exists() else 0, 0)


if __name__ == "__main__":
    unittest.main()
