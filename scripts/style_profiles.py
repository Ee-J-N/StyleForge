"""Style sample parsing, measurable profiles and explicitly confirmed feedback."""

from __future__ import annotations

import collections
import difflib
import html
import os
import re
import shutil
import statistics
import uuid
import zipfile
from html.parser import HTMLParser
from pathlib import Path

from sf_core import SCHEMA, child, copy_original, file_hash, identifier, now, read_json, validate_receipt, write_json, write_text

SUPPORTED = {".md", ".markdown", ".txt", ".html", ".htm", ".docx", ".pdf"}
PREFERENCE_FIELDS = {"tone", "expressions", "sentences", "paragraphs", "structure", "reasoning", "code_payload", "markdown", "images", "avoid", "notes"}


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if self.skip:
            return
        attrs = dict(attrs)
        if tag == "img":
            self.parts.append(f"\n![{attrs.get('alt', '')}]({attrs.get('src', '')})\n")
        elif tag in ("p", "div", "br", "li", "h1", "h2", "h3", "pre"):
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag in ("p", "div", "h1", "h2", "h3", "pre") and not self.skip:
            self.parts.append("\n\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def parse_document(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"Unsupported sample format: {suffix}")
    if suffix == ".docx":
        from docx import Document
        document = Document(path)
        text = "\n\n".join(p.text for p in document.paragraphs)
        return text, {"format": "docx", "image_count": len(document.inline_shapes), "image_layout": "requires agent inspection"}
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        return text, {"format": "pdf", "image_count": sum(len(page.images) for page in reader.pages), "image_layout": "requires agent inspection"}
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"Unrecognized text encoding: {path}")
    if suffix in (".html", ".htm"):
        parser = HTMLText()
        parser.feed(text)
        text = html.unescape("".join(parser.parts)) + "\n\n" + "\n".join(re.findall(r"<img\b[^>]*>", text, re.I))
        # Raw image tags retain width hints; avoid counting them twice below.
    return text, {"format": suffix.lstrip(".")}


def mean(values):
    return round(statistics.mean(values), 4) if values else 0


def measure(text, metadata=None):
    metadata = metadata or {}
    # Metadata and editor format controls are not the author's prose rhythm.
    text = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.S)
    text = re.sub(r"[\u200b-\u200f\ufeff]", "", text)
    fences = re.findall(r"(?ms)^```([^\n]*)\n.*?^```[ \t]*$|^~~~([^\n]*)\n.*?^~~~[ \t]*$", text)
    prose = re.sub(r"(?ms)^(`{3,}|~{3,})[^\n]*\n.*?^\1[ \t]*$", "", text)
    md_images = list(re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", prose))
    html_images = list(re.finditer(r"<img\b[^>]*>", prose, re.I))
    images = md_images if metadata.get("format") in ("html", "htm") else md_images + html_images
    image_contexts = [prose[max(0, m.start() - 160): min(len(prose), m.end() + 160)] for m in images]
    image_before = [next((p.strip() for p in reversed(re.split(r"\n\s*\n", prose[:m.start()])) if p.strip()), "") for m in images]
    image_after = [next((p.strip() for p in re.split(r"\n\s*\n", prose[m.end():]) if p.strip()), "") for m in images]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", prose) if p.strip() and not re.match(r"^(?:#|!\[|<img|\|)", p.strip())]
    plain = re.sub(r"!\[[^\]]*\]\([^)]+\)|<[^>]+>", "", prose)
    plain = re.sub(r"`[^`]+`", "", plain)
    sentences = [s.strip() for s in re.split(r"[。！？!?\n]+|(?<=[a-zA-Z])\.(?:\s|$)", plain) if s.strip()]
    lengths = [len(p) for p in paragraphs]
    lexical = {key: len(re.findall(pattern, plain)) for key, pattern in {
        "first_person": r"我们|我|本人",
        "colloquial": r"这里|先看|直接|试了|跑一下|看了下|坑|搞定|拿到",
        "formal": r"因此|由此|根据|验证|可以得到|可知|分析表明",
        "reasoning": r"因为|所以|说明|意味着|判断|原因|于是|但是|不过",
    }.items()}
    return {
        "prose_characters": len(plain),
        "sentence_characters_mean": mean([len(s) for s in sentences]),
        "paragraph_characters_mean": mean(lengths),
        "paragraph_count": len(paragraphs),
        "heading_count": len(re.findall(r"(?m)^#{1,6}\s+", text)),
        "numbered_heading_count": len(re.findall(r"(?m)^#{1,6}\s+(?:\d|[一二三四五六七八九十])", text)),
        "list_line_count": len(re.findall(r"(?m)^\s*(?:[-*+] |\d+[.)] )", text)),
        "table_line_count": len(re.findall(r"(?m)^\|.+\|\s*$", text)),
        "bold_count": len(re.findall(r"\*\*[^*]+\*\*", prose)),
        "code_block_count": len(fences),
        "code_languages": dict(collections.Counter((a or b).strip() or "unspecified" for a, b in fences)),
        "inline_code_count": len(re.findall(r"(?<!`)`[^`\n]+`(?!`)", prose)),
        "image_count": metadata.get("image_count", len(images)),
        "images_per_1000_characters": round(len(images) * 1000 / max(1, len(plain)), 4),
        "image_positions": [round(m.start() / max(1, len(prose)), 3) for m in images],
        "image_context_characters_mean": mean([len(c) for c in image_contexts]),
        "image_before_paragraph_characters_mean": mean([len(p) for p in image_before]),
        "image_after_paragraph_characters_mean": mean([len(p) for p in image_after]),
        "image_width_values": re.findall(r"(?:width\s*=\s*['\"]?|width:\s*)(\d+(?:px|%)?)", text, re.I),
        "image_numbered_count": sum(bool(re.search(r"(?:图|Figure|Fig\.?)[ -]?\d+", c, re.I)) for c in image_contexts),
        "image_annotation_mentions": sum(bool(re.search(r"标注|箭头|红框|圈出|annotation", c, re.I)) for c in image_contexts),
        "terminal_image_mentions": sum(bool(re.search(r"终端|terminal|console|命令行", c, re.I)) for c in image_contexts),
        "source_image_mentions": sum(bool(re.search(r"源码|source|反编译|代码截图|IDA", c, re.I)) for c in image_contexts),
        "image_layout_confidence": metadata.get("image_layout", "positions measured; semantics need agent review"),
        "lexical_counts": lexical,
    }


def summarize(samples):
    numeric = [key for key, value in samples[0]["metrics"].items() if isinstance(value, (int, float))]
    stats = {}
    for key in numeric:
        values = [sample["metrics"][key] for sample in samples]
        stats[key] = {"mean": mean(values), "min": min(values), "max": max(values), "sample_count": len(values)}
    lexical = {key: mean([s["metrics"]["lexical_counts"][key] * 1000 / max(1, s["metrics"]["prose_characters"]) for s in samples]) for key in samples[0]["metrics"]["lexical_counts"]}
    return {"documents": len(samples), "statistics": stats, "lexical_per_1000_characters": lexical,
            "image_width_values": sorted({v for s in samples for v in s["metrics"]["image_width_values"]}),
            "image_positions": [v for s in samples for v in s["metrics"]["image_positions"]],
            "confidence": "limited corpus" if len(samples) < 5 else "measured corpus; qualitative analysis still required"}


def save_version(folder, profile):
    current = folder / "profile.json"
    if current.exists():
        old = read_json(current)
        write_json(folder / "history" / f"v{old['version']:04d}.json", old)
    write_json(current, profile)


def snapshot_sample(source, folder, text):
    source = Path(source).resolve(strict=True)
    original = copy_original(source, folder / "original")
    normalized = folder / "normalized" / "article.md"
    write_text(normalized, text)
    assets = []
    references = re.findall(r"!\[[^\]]*\]\(<?([^)>]+)>?\)|<img\b[^>]*src=['\"]([^'\"]+)", text, re.I)
    for pair in references:
        relative = pair[0] or pair[1]
        if re.match(r"(?:[a-z]+:|/|\\)", relative, re.I):
            assets.append({"source": relative, "status": "external_not_copied"})
            continue
        try:
            asset = child(source.parent, relative)
            if not asset.is_file():
                raise ValueError("Local image not found")
            for base in (original.parent, normalized.parent):
                target = child(base, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copy2(asset, target)
            assets.append({"source": str(asset), "path": relative, "sha256": file_hash(asset), "status": "preserved"})
        except (ValueError, OSError) as error:
            assets.append({"source": relative, "status": "unresolved", "error": str(error)})
    return original, normalized, assets


def learn(ctx, name, author, paths, source_kind="user_designated", source_note="", update=False):
    identifier(name)
    identifier(author)
    if source_kind not in ("historical_user", "external_author", "user_designated", "fixture"):
        raise ValueError("Unconfirmed generated writing is not a style sample source")
    if source_kind == "fixture" and not ctx.test:
        raise ValueError("Synthetic samples belong in an explicitly marked fixture store")
    folder = ctx.profile_dir(name)
    if (folder / "profile.json").exists():
        if not update:
            raise ValueError("Profile exists; use --update to add samples")
        profile = ctx.profile(name)
        if profile["author_id"] != author:
            raise ValueError("A profile must contain exactly one declared author")
    else:
        profile = {"schema_version": SCHEMA, "id": name, "owner_user": ctx.user, "author_id": author,
                   "created_at": now(), "version": 0, "samples": [], "preferences": {}, "qualitative_analysis": {}, "feedback": []}
    sources = []
    for supplied in paths:
        supplied = Path(supplied).resolve(strict=True)
        sources.extend(sorted(p for p in supplied.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED) if supplied.is_dir() else [supplied])
    known = {sample["sha256"] for sample in profile["samples"]}
    sample_root = folder / "samples"
    staging = sample_root / (".learn-" + uuid.uuid4().hex)
    additions = []
    committed = []
    profile_saved = False
    try:
        for source in sources:
            checksum = file_hash(source)
            if checksum in known:
                continue
            text, metadata = parse_document(source)
            if not text.strip():
                raise ValueError(f"No readable text extracted from sample: {source}")
            sample_id = "sample-" + checksum[:16]
            sample_folder = staging / sample_id
            original, normalized, assets = snapshot_sample(source, sample_folder, text)
            final_sample = Path("samples") / sample_id
            sample = {"id": sample_id, "author_id": author, "source_kind": source_kind, "source_note": source_note,
                      "source_path": str(source), "imported_at": now(), "sha256": checksum,
                      "original_path": (final_sample / original.relative_to(sample_folder)).as_posix(),
                      "normalized_path": (final_sample / normalized.relative_to(sample_folder)).as_posix(),
                      "assets": assets, "parser_metadata": metadata, "metrics": measure(text, metadata)}
            additions.append((sample_id, sample))
            known.add(checksum)
        if not profile["samples"] and not additions:
            raise ValueError("No eligible writing samples were provided")
        for sample_id, sample in additions:
            destination = sample_root / sample_id
            staged = staging / sample_id
            if destination.exists():
                raise ValueError(f"A sample directory already exists outside its profile record: {destination}")
            os.rename(staged, destination)
            committed.append(destination)
            profile["samples"].append(sample)
        if not additions and not profile["samples"]:
            raise ValueError("No eligible writing samples were provided")
        for sample in profile["samples"]:
            sample_text = child(folder, sample["normalized_path"]).read_text(encoding="utf-8")
            sample["metrics"] = measure(sample_text, sample.get("parser_metadata"))
        profile["measurements"] = summarize(profile["samples"])
        profile["version"] += 1
        profile["updated_at"] = now()
        profile["source_authorship"] = "declared_by_user; do not infer identity from folder names"
        save_version(folder, profile)
        profile_saved = True
    except Exception:
        if not profile_saved:
            for path in committed:
                if path.exists():
                    shutil.rmtree(path)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return profile


def edit(ctx, name, patch):
    profile = ctx.profile(name)
    if set(patch) - {"preferences", "qualitative_analysis"}:
        raise ValueError("Only preferences and qualitative_analysis are editable; measured provenance is preserved")
    preferences = patch.get("preferences", {})
    if not isinstance(preferences, dict) or set(preferences) - PREFERENCE_FIELDS:
        raise ValueError("Unsupported preference fields")
    if "qualitative_analysis" in patch:
        analysis = patch["qualitative_analysis"]
        if not isinstance(analysis, dict):
            raise ValueError("Qualitative analysis must be an object")
        if any(sample_id not in {s["id"] for s in profile["samples"]} for sample_id in analysis.get("basis_sample_ids", [])):
            raise ValueError("Qualitative analysis references unknown samples")
        profile["qualitative_analysis"] = analysis
    profile["preferences"].update(preferences)
    profile["version"] += 1
    profile["updated_at"] = now()
    save_version(ctx.profile_dir(name), profile)
    return profile


def export_profile(ctx, name, output, include_samples=False):
    profile = ctx.profile(name)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Export destination exists; select a new file")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".zip":
        folder = ctx.profile_dir(name)
        with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("profile.json", __import__("json").dumps(profile, ensure_ascii=False, indent=2))
            if include_samples:
                for path in sorted((folder / "samples").rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(folder).as_posix())
    else:
        if include_samples:
            raise ValueError("Use a ZIP destination when including original samples")
        write_json(output, profile)
    return {"path": str(output), "sha256": file_hash(output), "includes_samples": include_samples}


def delete_profile(ctx, name):
    profile = ctx.profile(name)
    active = []
    for path in (ctx.owner / "cases").glob("*/case.json"):
        case = read_json(path)
        if case.get("profile_id") == name:
            active.append(case["id"])
    token = uuid.uuid4().hex
    destination = child(ctx.owner, "trash", "profiles", token)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(ctx.profile_dir(name)), str(destination))
    return {"deleted_profile": profile["id"], "restore_token": token, "affected_cases": active, "note": "Reversible deletion; original user files are unchanged"}


def restore_profile(ctx, token):
    if not isinstance(token, str) or not re.fullmatch(r"(?:[a-f0-9]{32}|[A-Za-z0-9][A-Za-z0-9_-]{0,79}-[a-f0-9]{12})", token):
        raise ValueError("Invalid restore token")
    folder = child(ctx.owner, "trash", "profiles", token)
    profile = read_json(folder / "profile.json")
    if profile["owner_user"] != ctx.user:
        raise ValueError("Ownership mismatch")
    destination = ctx.profile_dir(profile["id"])
    if destination.exists():
        raise ValueError("A profile with this identifier already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(folder), str(destination))
    return {"restored": profile["id"]}


def feedback(ctx, name, before, edited, receipt_path, preference_patch=None):
    profile = ctx.profile(name)
    receipt = validate_receipt(ctx, receipt_path, edited)
    before_text, _ = parse_document(before)
    edited_text, metadata = parse_document(edited)
    folder = ctx.profile_dir(name)
    checksum = file_hash(edited)
    sample_id = "sample-" + checksum[:16]
    if any(s["sha256"] == checksum for s in profile["samples"]):
        raise ValueError("This confirmed article is already part of the profile")
    sample_folder = folder / "samples" / sample_id
    original, normalized, assets = snapshot_sample(edited, sample_folder, edited_text)
    copy_original(receipt_path, sample_folder, "confirmation-")
    diff = "".join(difflib.unified_diff(before_text.splitlines(True), edited_text.splitlines(True), fromfile="generated", tofile="user-edited"))
    write_text(sample_folder / "user-edits.diff", diff)
    profile["samples"].append({"id": sample_id, "author_id": profile["author_id"], "source_kind": "approved_generated",
        "source_note": receipt["confirmation_ref"], "source_path": str(Path(edited).resolve()), "imported_at": now(), "sha256": checksum,
        "original_path": original.relative_to(folder).as_posix(), "normalized_path": normalized.relative_to(folder).as_posix(),
        "assets": assets, "parser_metadata": metadata, "metrics": measure(edited_text, metadata)})
    patch = preference_patch or {}
    if set(patch) - PREFERENCE_FIELDS:
        raise ValueError("Unsupported feedback preference field")
    profile["preferences"].update(patch)
    profile["feedback"].append({"at": now(), "before_sha256": file_hash(before), "approved_sha256": checksum,
                                "confirmation_ref": receipt["confirmation_ref"], "sample_id": sample_id, "preferences_changed": patch})
    profile["measurements"] = summarize(profile["samples"])
    profile["version"] += 1
    profile["updated_at"] = now()
    save_version(folder, profile)
    return profile
