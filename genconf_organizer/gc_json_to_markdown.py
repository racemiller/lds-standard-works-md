#!/usr/bin/env python3
"""
gc_json_to_markdown.py

Convert the scraper's JSON output into one Markdown file per talk, ready to
drop into an OpenWebUI knowledge collection.

Each file gets YAML frontmatter (machine-readable metadata) AND a short plain
header line inside the body. The duplicated header is deliberate: depending on
how OpenWebUI chunks documents it may ignore frontmatter, so repeating the
title/speaker/conference as body text keeps them searchable and citable.

By default, files are grouped into per-conference subfolders named like
`2024-April/`; pass --flat to write them all into one directory instead.

Output path:  <out>/YYYY-Month/YYYY-MM-speaker-title-slug.md   (sortable)

Field detection is defensive (see gc_common.py). Talks whose body looks like it
contains the repeated-stanza artifact are tagged `needs_review: true` in the
frontmatter and reported on stderr — they are NOT silently altered.

Examples
--------
    python gc_json_to_markdown.py ./scraper_output --out ./markdown
    python gc_json_to_markdown.py ./scraper_output --out ./markdown --flat
    python gc_json_to_markdown.py talks.json --out ./markdown
"""

import argparse
import json
import sys
from pathlib import Path

import gc_common as gc


def _yaml_scalar(value) -> str:
    """A JSON string is a valid YAML double-quoted scalar, so reuse it for safe escaping."""
    if value is None:
        return "null"
    return json.dumps(str(value), ensure_ascii=False)


def build_markdown(rec: dict, needs_review: bool) -> str:
    title = rec["title"] or "Untitled"
    speaker = rec["speaker"] or "Unknown speaker"
    conference = rec["conference"] or "General Conference"

    fm = [
        "---",
        f"title: {_yaml_scalar(title)}",
        f"speaker: {_yaml_scalar(speaker)}",
        f"date: {_yaml_scalar(rec['date_iso'])}",
        f"conference: {_yaml_scalar(conference)}",
        f"order: {rec['order']}",
        f"source: {_yaml_scalar(rec['url'])}",
        f"needs_review: {'true' if needs_review else 'false'}",
        "---",
    ]
    header = f"# {title}\n\n**{speaker}** — {conference}"
    return "\n".join(fm) + "\n\n" + header + "\n\n" + rec["body"] + "\n"


def make_filename(rec: dict, used: set) -> str:
    date_part = rec["date_iso"] or "0000-00"
    stem = "-".join(filter(None, [
        date_part,
        f"{rec['order']:02d}",  # speaking order within the conference
        gc.slugify(rec["speaker"] or "unknown", 30),
        gc.slugify(rec["title"] or "untitled", 50),
    ]))
    name = f"{stem}.md"
    n = 2
    while name in used:
        name = f"{stem}-{n}.md"
        n += 1
    used.add(name)
    return name


def iter_input_files(path: Path):
    if path.is_dir():
        yield from sorted(path.glob("*.json"))
        yield from sorted(path.glob("*.jsonl"))
    else:
        yield path


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", help="A JSON/JSONL file, or a directory of them.")
    p.add_argument("--out", required=True, help="Output directory for .md files.")
    p.add_argument("--flat", action="store_true",
                   help="Write all .md files directly into --out instead of "
                        "grouping them into per-conference subfolders "
                        "(e.g. 2024-April/).")
    args = p.parse_args(argv)

    in_path = Path(args.input)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    used_names: dict = {}  # folder -> set of names used in that folder
    seq_by_conf: dict = {}  # conference key -> running talk count
    written = skipped = flagged = 0
    folders: set = set()

    for jf in iter_input_files(in_path):
        try:
            talks = gc.load_json_any(jf)
        except json.JSONDecodeError as e:
            print(f"  ! could not parse {jf.name}: {e}", file=sys.stderr)
            continue

        for talk in talks:
            rec = gc.normalize_talk(talk)
            if not rec["body"]:
                skipped += 1
                print(f"  - skipped (no body): {rec['title'] or jf.name}",
                      file=sys.stderr)
                continue

            report = gc.detect_duplication(rec["body"])
            if report["flagged"]:
                flagged += 1
                note = f"score={report['score']}"
                if report["repeated"]:
                    note += f", top-repeat x{report['repeated'][0][1]}"
                print(f"  ~ review: {rec['title'] or '(untitled)'} [{note}]",
                      file=sys.stderr)

            # Speaking order within the conference: talks arrive in order in
            # each period's JSON, so number them as encountered (skipped/
            # empty-body talks above don't consume a number).
            conf_key = rec["date_iso"] or "unknown"
            rec["order"] = seq_by_conf[conf_key] = seq_by_conf.get(conf_key, 0) + 1

            # Choose destination directory.
            if args.flat:
                target_dir = out_dir
            else:
                target_dir = out_dir / gc.conference_folder(rec["date_iso"])
                if target_dir not in folders:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    folders.add(target_dir)

            used = used_names.setdefault(str(target_dir), set())
            fname = make_filename(rec, used)
            (target_dir / fname).write_text(
                build_markdown(rec, report["flagged"]), encoding="utf-8"
            )
            written += 1

    layout = "flat" if args.flat else f"{len(folders)} conference folders"
    print(f"\nDone: {written} written ({layout}), {flagged} flagged for review, "
          f"{skipped} skipped -> {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
