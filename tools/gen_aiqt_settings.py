#!/usr/bin/env python3
"""Merge the vendored AIQT hooks into .claude/settings.json.

The plugin hooks.json and the settings.json "hooks" object share one schema, so this is a path
rewrite plus a merge: ${CLAUDE_PLUGIN_ROOT} becomes ${CLAUDE_PROJECT_DIR}/.aiqt/hooks, because the
hooks are vendored into this repo rather than installed as a plugin.

This MERGES. Any settings already in the file are preserved, including hooks this repo does not
own (the fleet inbox Stop hook and status line are wired by the custodian, not by us). AIQT-owned
hook groups are identified by the vendored script path appearing in their command or args, so a
re-run replaces exactly those and leaves every other entry untouched. That makes the script
idempotent without needing marker keys the settings schema does not define.

Re-run after every upgrade of the pinned vendor tree; see .aiqt/PIN.

  tools/gen_aiqt_settings.py            merge and write
  tools/gen_aiqt_settings.py --check    verify the file is already in the merged state, write nothing
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / ".aiqt" / "hooks" / "hooks.json"
DST = ROOT / ".claude" / "settings.json"
PLUGIN_ROOT = "${CLAUDE_PLUGIN_ROOT}"
PROJECT_ROOT = "${CLAUDE_PROJECT_DIR}/.aiqt/hooks"
OWNED_MARKER = ".aiqt/hooks"


def rewrite(node):
    if isinstance(node, str):
        return node.replace(PLUGIN_ROOT, PROJECT_ROOT)
    if isinstance(node, list):
        return [rewrite(x) for x in node]
    if isinstance(node, dict):
        return {k: rewrite(v) for k, v in node.items()}
    return node


def is_ours(group):
    """True when a hook group runs the vendored AIQT script. Identification is by path, so a
    re-run replaces our own entries and never a hook someone else wired."""
    for entry in group.get("hooks", []):
        blob = " ".join([str(entry.get("command", ""))] +
                        [str(a) for a in entry.get("args", [])])
        if OWNED_MARKER in blob:
            return True
    return False


def merge(existing, ours):
    """Per event, keep every foreign group in its original order, then append ours."""
    out = dict(existing)
    hooks = {k: list(v) for k, v in (existing.get("hooks") or {}).items()}
    for event, groups in ours.items():
        kept = [g for g in hooks.get(event, []) if not is_ours(g)]
        hooks[event] = kept + list(groups)
    out["hooks"] = hooks
    return out


def render():
    manifest = json.loads(SRC.read_text(encoding="utf-8"))
    hooks = manifest.get("hooks")
    if not hooks:
        raise SystemExit("FAIL: no hooks object in {}".format(SRC))
    ours = rewrite(hooks)
    existing = {}
    if DST.exists():
        existing = json.loads(DST.read_text(encoding="utf-8"))
    merged = merge(existing, ours)
    return ours, json.dumps(merged, indent=2) + "\n"


def main(argv):
    ours, text = render()
    if "--check" in argv:
        if not DST.exists():
            print("  SKIP  .claude/settings.json absent; AIQT hooks are not activated")
            return 0
        if DST.read_text(encoding="utf-8") != text:
            print("  FAIL  .claude/settings.json is stale; run tools/gen_aiqt_settings.py")
            return 1
        print("  ok    .claude/settings.json carries the pinned AIQT hooks")
        return 0
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(text, encoding="utf-8")
    count = sum(len(v) for v in ours.values())
    print("merged {} AIQT hook groups across {} events into {}".format(
        count, len(ours), DST.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
