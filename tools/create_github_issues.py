"""Create the GitHub labels, milestones and issues of tools/work_items.json with the GitHub CLI.

Usage:
    python tools/create_github_issues.py            # dry run: print what would be created
    python tools/create_github_issues.py --apply    # create on GitHub (needs `gh auth login`)

Issues are created in file order; "depends" entries are written as links to the already created issues.
"""

import argparse
import json
import pathlib
import re
import subprocess
import sys

ITEMS_FILE = pathlib.Path(__file__).with_name("work_items.json")


def gh(args, apply):
    if not apply:
        print("gh " + " ".join(f'"{a}"' if " " in a or "\n" in a else a for a in args).replace("\n", "\\n"))
        return ""
    result = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        sys.exit(f"gh {' '.join(args[:3])} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def existing_milestones(apply):
    if not apply:
        return {}
    out = gh(["api", "repos/{owner}/{repo}/milestones?state=all&per_page=100"], apply)
    return {m["title"]: m["number"] for m in json.loads(out or "[]")}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="really create labels, milestones and issues")
    args = parser.parse_args()

    data = json.loads(ITEMS_FILE.read_text(encoding="utf-8"))

    for name, color in data["labels"].items():
        gh(["label", "create", name, "--color", color, "--force"], args.apply)

    known = existing_milestones(args.apply)
    for title, description in data["milestones"].items():
        if title not in known:
            gh(["api", "repos/{owner}/{repo}/milestones", "-f", f"title={title}", "-f", f"description={description}"],
               args.apply)

    numbers = {}
    for item in data["items"]:
        body = item["body"]
        deps = item.get("depends", [])
        if deps:
            refs = ", ".join(f"#{numbers[d]}" if d in numbers else d for d in deps)
            body += f"\n\nDepends on: {refs}"
        body += f"\n\nWork item {item['id']} (tools/work_items.json)."
        cmd = ["issue", "create", "--title", f"{item['id']} {item['title']}", "--body", body,
               "--milestone", item["milestone"]]
        for label in item["labels"]:
            cmd += ["--label", label]
        url = gh(cmd, args.apply)
        match = re.search(r"/issues/(\d+)$", url)
        if match:
            numbers[item["id"]] = match.group(1)

    print(f"{'Created' if args.apply else 'Dry run:'} {len(data['labels'])} labels, "
          f"{len(data['milestones'])} milestones, {len(data['items'])} issues")


if __name__ == "__main__":
    main()
