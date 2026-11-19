"""Read-only export of explicitly selected SiYuan documents for style learning."""

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

from sf_core import child, file_hash, now, readable_name, write_json, write_text


def api(base, route, data):
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("STYLEFORGE_SIYUAN_TOKEN")
    if token:
        headers["Authorization"] = "Token " + token
    request = urllib.request.Request(base.rstrip("/") + "/api/" + route, data=json.dumps(data).encode(), headers=headers)
    with urllib.request.urlopen(request, timeout=25) as response:
        result = json.load(response)
    if result.get("code") != 0:
        raise ValueError(f"SiYuan API {route}: {result.get('msg', 'unknown error')}")
    return result.get("data")


def export(base, hpath, output, notebook=None):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output directory; prior exports are preserved")
    box_filter = ""
    if notebook:
        notebooks = api(base, "notebook/lsNotebooks", {})["notebooks"]
        boxes = [box["id"] for box in notebooks if box["name"].casefold() == notebook.casefold()]
        if len(boxes) != 1:
            raise ValueError("Notebook name must identify exactly one notebook")
        box_filter = " AND box='" + boxes[0].replace("'", "''") + "'"
    escaped = hpath.rstrip("/").replace("'", "''")
    statement = f"SELECT id,hpath,box,path FROM blocks WHERE type='d' AND hpath LIKE '{escaped}/%'" + box_filter + " ORDER BY hpath"
    # SiYuan's SQL gateway does not accept every SQLite ESCAPE expression.
    # Exact prefix filtering keeps wildcard characters in the chosen path local.
    docs = [doc for doc in (api(base, "query/sql", {"stmt": statement}) or []) if doc["hpath"].startswith(hpath.rstrip("/") + "/")]
    if not docs:
        raise ValueError("No documents found below the selected SiYuan path")
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for document in docs:
        exported = api(base, "export/exportMdContent", {"id": document["id"]})
        content = exported["content"]
        path = output / f"{document['id']}-{readable_name(document['hpath'].split('/')[-1])}.md"
        write_text(path, content.rstrip() + "\n")
        assets = []
        for asset in sorted(set(re.findall(r"(?:\]\(|src=[\"])(assets/[^)\"\s]+)", content))):
            target = child(output, urllib.parse.unquote(asset))
            headers = {}
            token = os.environ.get("STYLEFORGE_SIYUAN_TOKEN")
            if token:
                headers["Authorization"] = "Token " + token
            try:
                request = urllib.request.Request(base.rstrip("/") + "/" + urllib.parse.quote(asset, safe="/-%"), headers=headers)
                with urllib.request.urlopen(request, timeout=20) as response:
                    raw = response.read()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                assets.append({"path": asset, "sha256": file_hash(target), "status": "exported"})
            except Exception as error:
                assets.append({"path": asset, "status": "missing", "error": str(error)})
        records.append({**document, "export_path": str(path), "sha256": file_hash(path),
                        "source_uri": "siyuan://blocks/" + document["id"], "assets": assets})
    manifest = {"exported_at": now(), "read_only": True, "api": base, "hpath": hpath, "notebook": notebook,
                "actual_document_count": len(records), "authorship": "user-designated reference; not automatically attributed", "documents": records}
    write_json(output / "source-manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:6806")
    parser.add_argument("--hpath", required=True)
    parser.add_argument("--notebook")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.api, args.hpath, args.output, args.notebook), ensure_ascii=False, indent=2))
