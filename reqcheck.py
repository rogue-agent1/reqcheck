#!/usr/bin/env python3
"""reqcheck - Check Python requirements for outdated/vulnerable packages.

One file. Zero deps. Audit your deps.

Usage:
  reqcheck.py check requirements.txt    → check installed vs required
  reqcheck.py parse requirements.txt    → parse and list deps
  reqcheck.py freeze                    → show installed packages
  reqcheck.py diff req1.txt req2.txt    → compare two requirements files
  reqcheck.py unused src/ req.txt       → find potentially unused deps
"""

import argparse
import json
import os
import re
import subprocess
import sys


def parse_requirements(path: str) -> list[dict]:
    deps = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            m = re.match(r'^([a-zA-Z0-9_.-]+)\s*([><=!~]+.+)?$', line)
            if m:
                deps.append({"name": m.group(1).lower(), "spec": (m.group(2) or "").strip(), "raw": line})
    return deps


def get_installed() -> dict:
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "list", "--format=json"],
                          capture_output=True, text=True, timeout=30)
        pkgs = json.loads(r.stdout)
        return {p["name"].lower(): p["version"] for p in pkgs}
    except Exception:
        return {}


def cmd_check(args):
    deps = parse_requirements(args.file)
    installed = get_installed()
    if not deps:
        print("No dependencies found")
        return

    missing = 0
    for d in deps:
        ver = installed.get(d["name"], installed.get(d["name"].replace("-", "_")))
        if ver:
            print(f"  ✅ {d['name']:30s} {ver:15s} {d['spec']}")
        else:
            print(f"  ❌ {d['name']:30s} {'NOT INSTALLED':15s} {d['spec']}")
            missing += 1

    print(f"\n  {len(deps)} packages, {len(deps)-missing} installed, {missing} missing")
    return 1 if missing else 0


def cmd_parse(args):
    deps = parse_requirements(args.file)
    for d in deps:
        spec = d['spec'] or '(any)'
        print(f"  {d['name']:30s} {spec}")
    print(f"\n  {len(deps)} packages")


def cmd_freeze(args):
    installed = get_installed()
    for name in sorted(installed):
        print(f"{name}=={installed[name]}")
    print(f"\n# {len(installed)} packages", file=sys.stderr)


def cmd_diff(args):
    deps1 = {d["name"]: d for d in parse_requirements(args.file1)}
    deps2 = {d["name"]: d for d in parse_requirements(args.file2)}
    all_names = sorted(set(deps1) | set(deps2))

    added = removed = changed = 0
    for name in all_names:
        in1 = deps1.get(name)
        in2 = deps2.get(name)
        if in1 and not in2:
            print(f"  - {name} {in1['spec']}")
            removed += 1
        elif in2 and not in1:
            print(f"  + {name} {in2['spec']}")
            added += 1
        elif in1["spec"] != in2["spec"]:
            print(f"  ~ {name} {in1['spec']} → {in2['spec']}")
            changed += 1

    print(f"\n  +{added} -{removed} ~{changed}")


def cmd_unused(args):
    deps = parse_requirements(args.req)
    src_dir = args.src

    # Scan all Python files for import statements
    imports = set()
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".venv", "venv", "node_modules")]
        for f in files:
            if f.endswith(".py"):
                try:
                    with open(os.path.join(root, f)) as fh:
                        for line in fh:
                            m = re.match(r'^(?:from|import)\s+([a-zA-Z0-9_]+)', line)
                            if m:
                                imports.add(m.group(1).lower())
                except Exception:
                    pass

    # Common name mappings (package name → import name)
    mappings = {
        "pillow": "pil", "scikit-learn": "sklearn", "pyyaml": "yaml",
        "python-dateutil": "dateutil", "beautifulsoup4": "bs4",
    }

    unused = []
    for d in deps:
        import_name = mappings.get(d["name"], d["name"].replace("-", "_"))
        if import_name not in imports and d["name"] not in imports:
            unused.append(d["name"])

    if unused:
        print("Potentially unused packages:")
        for name in unused:
            print(f"  ⚠️  {name}")
        print(f"\n  {len(unused)} potentially unused (verify manually)")
    else:
        print("All packages appear to be used")


def main():
    p = argparse.ArgumentParser(description="Check Python requirements")
    sub = p.add_subparsers(dest="cmd")

    for name in ("check", "parse"):
        s = sub.add_parser(name)
        s.add_argument("file")

    sub.add_parser("freeze")

    s = sub.add_parser("diff")
    s.add_argument("file1")
    s.add_argument("file2")

    s = sub.add_parser("unused")
    s.add_argument("src")
    s.add_argument("req")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        return 1

    cmds = {"check": cmd_check, "parse": cmd_parse, "freeze": cmd_freeze,
            "diff": cmd_diff, "unused": cmd_unused}
    return cmds[args.cmd](args) or 0


if __name__ == "__main__":
    sys.exit(main())
