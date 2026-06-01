#!/usr/bin/env bash
# CI helper: fail if any <EmptyState> JSX call lacks a `testid=` prop.
#
# Run via: bash scripts/check-empty-states.sh
# Exit 0 = clean, exit 1 = at least one violation found.
#
# Catches future contributors who add an EmptyState without wiring its testid,
# silently losing automated coverage of the empty case. Cheap dev-time check.
# Note: we do NOT use `set -e` because we want to count violations across all
# files, not abort on the first one.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/frontend/src"
viol=0
# We use Python directly for the regex match (handles multi-line cleanly), so
# the system-level pcregrep / grep -P availability is irrelevant. Kept here in
# case future contributors prefer a pure-shell implementation.

# Find every file containing <EmptyState (skip the component file itself
# since its JSDoc has a usage example with no testid by design).
files=$(grep -rl "<EmptyState" "$SRC" --include="*.jsx" --include="*.js" 2>/dev/null | grep -v "/components/EmptyState\\.jsx$" || true)

for f in $files; do
  # Pull each EmptyState JSX call (greedy match between <EmptyState and the closing > of the opening tag)
  python3 - "$f" << 'PY'
import re, sys
path = sys.argv[1]
src = open(path).read()
# Match <EmptyState ... /> across lines. EmptyState is always self-closing in
# this codebase. Using `[\s\S]*?` to be greedy across `=>` arrow syntax (which
# contains a `>` that broke the previous `[^>]*?` form).
pattern = re.compile(r"<EmptyState\b[\s\S]*?/>", re.DOTALL)
violations = []
for m in pattern.finditer(src):
    tag = m.group(0)
    if "testid=" not in tag and "data-testid=" not in tag:
        # Compute the line number for a friendlier error
        line_no = src.count("\n", 0, m.start()) + 1
        violations.append((line_no, tag.replace("\n", " ")[:120]))
if violations:
    for ln, snip in violations:
        print(f"  {path}:{ln}  {snip}")
    sys.exit(2)
PY
  rc=$?
  if [ "$rc" -ne 0 ]; then
    viol=$((viol + 1))
  fi
done

if [ "$viol" -gt 0 ]; then
  echo ""
  echo "❌ $viol file(s) contain <EmptyState> without a testid prop."
  echo "   Add testid=\"page-something-empty\" to each violating call so e2e tests can target it."
  exit 1
fi
echo "✓ All <EmptyState> JSX calls include a testid prop."
