#!/usr/bin/env python3
"""
validate_talks.py

Scan talks for the duplicated-stanza / repeated-text artifact and report which
ones need a human look. Works on either:
  - the scraper's JSON/JSONL output, or
  - a directory of the .md files produced by gc_json_to_markdown.py

With --fix, writes CONSERVATIVELY cleaned copies to a separate directory
(collapsing only immediately-adjacent identical lines/sentences). It never
overwrites your originals, and files may still need manual review afterward.

Examples
--------
    python validate_talks.py ./markdown
    python validate_talks.py ./scraper_output --json
    python validate_talks.py ./markdown --fix ./markdown_cleaned
"""

import argparse
import sys
from pathlib import Path

import gc_common as gc


def _read_md(path: Path) -> tuple[str, str, str]:
    """
    Return (frontmatter, header_block, body) for a .md file produced by the
    converter. The converter writes: frontmatter \\n\\n header \\n\\n body, where
    header is "# Title\\n\\n**speaker** — conference". We split those off so the
    duplication check sees only the actual talk text, not the title/byline.
    """
    text = path.read_text(encoding="utf-8")
    frontmatter = ""
    remainder = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            frontmatter = "---" + parts[1] + "---"
            remainder = parts[2].lstrip("\n")
    # header is the first two double-newline-separated blocks (# title, byline)
    blocks = remainder.split("\n\n", 2)
    if len(blocks) == 3 and blocks[0].lstrip().startswith("#"):
        header_block = blocks[0] + "\n\n" + blocks[1]
        body = blocks[2]
    else:
        header_block, body = "", remainder
    return frontmatter, header_block, body


def iter_records(root: Path, as_json: bool):
    """Yield (label, body, write_back) tuples. write_back(new_body) rewrites a fixed copy."""
    if as_json:
        files = [root] if root.is_file() else sorted(
            list(root.glob("*.json")) + list(root.glob("*.jsonl")))
        for jf in files:
            for talk in gc.load_json_any(jf):
                rec = gc.normalize_talk(talk)
                label = rec["title"] or jf.name
                yield label, rec["body"], None
    else:
        files = [root] if root.is_file() else sorted(root.glob("*.md"))
        for mf in files:
            fm, header, body = _read_md(mf)
            yield mf.name, body, (mf, fm, header)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", help="Directory (or file) of .md, or scraper JSON with --json.")
    p.add_argument("--json", action="store_true",
                   help="Treat input as scraper JSON/JSONL instead of .md files.")
    p.add_argument("--fix", metavar="OUT_DIR", default=None,
                   help="Write conservatively cleaned copies here (.md input only).")
    p.add_argument("--threshold", type=float, default=0.15,
                   help="Duplicate-score threshold for flagging (default: 0.15).")
    args = p.parse_args(argv)

    root = Path(args.input)
    fix_dir = Path(args.fix) if args.fix else None
    if fix_dir:
        if args.json:
            p.error("--fix works on .md input only (it rewrites the file body).")
        fix_dir.mkdir(parents=True, exist_ok=True)

    total = flagged = fixed = 0
    for label, body, write_back in iter_records(root, args.json):
        total += 1
        report = gc.detect_duplication(body)
        if report["score"] >= args.threshold or report["consecutive"] or report["repeated"]:
            flagged += 1
            print(f"\nFLAG  {label}")
            print(f"      score={report['score']}  sentences={report['sentence_count']}")
            if report["consecutive"]:
                ex = report["consecutive"][0]
                print(f"      adjacent duplicate: \"{ex[:80]}...\"")
            for sent, count in report["repeated"][:2]:
                print(f"      repeated x{count}: \"{sent[:80]}...\"")

            if fix_dir and write_back:
                mf, fm, header = write_back
                cleaned = gc.collapse_adjacent_duplicates(body)
                after = gc.detect_duplication(cleaned)
                pieces = [p for p in (fm, header, cleaned) if p]
                out = "\n\n".join(pieces) + "\n"
                (fix_dir / mf.name).write_text(out, encoding="utf-8")
                fixed += 1
                still = "still flagged" if after["flagged"] else "looks clean now"
                print(f"      -> wrote cleaned copy ({still}, score {after['score']})")

    print(f"\n{flagged} of {total} talks flagged.", file=sys.stderr)
    if fix_dir:
        print(f"{fixed} cleaned copies written to {fix_dir} "
              f"(review the 'still flagged' ones).", file=sys.stderr)


if __name__ == "__main__":
    main()
