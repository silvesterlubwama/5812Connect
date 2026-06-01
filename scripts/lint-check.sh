#!/usr/bin/env bash
# Lint gate: blocks commits/PRs that introduce critical Python or JS issues.
# Run locally:   ./scripts/lint-check.sh
# Used by CI:    .github/workflows/ci.yml

set -e
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cd "$(dirname "$0")/.."

failed=0

echo -e "${YELLOW}[1/3] Python (ruff) — security & correctness rules${NC}"
# F841 = unused local var (often = abandoned variable, leftover logic)
# F821 = undefined name (runtime crash)
# F823 = local var referenced before assignment
# E722 = bare except (silently hides errors)
# B006 = mutable defaults (bug magnet)
# Note: B008 is excluded because FastAPI's `Depends()` pattern legitimately
# uses function calls in defaults — would be 600+ false positives.
if ruff check backend \
    --select F821,F823,F841,E722,B006 \
    --exclude backend/tests 2>&1; then
  echo -e "${GREEN}  ✓ Python production code clean${NC}"
else
  echo -e "${RED}  ✗ Python lint failures above${NC}"
  failed=1
fi

echo ""
echo -e "${YELLOW}[2/3] JavaScript (eslint) — quiet mode (errors only)${NC}"
cd frontend
# --quiet means ignore warnings; errors only block CI
if yarn -s eslint --quiet "src/**/*.{js,jsx}" 2>&1; then
  echo -e "${GREEN}  ✓ Frontend production code clean${NC}"
else
  echo -e "${RED}  ✗ Frontend lint errors above${NC}"
  failed=1
fi
cd ..

echo ""
echo -e "${YELLOW}[3/3] EmptyState testid coverage${NC}"
if bash scripts/check-empty-states.sh 2>&1; then
  : # already prints its own success line
else
  failed=1
fi

echo ""
if [ $failed -eq 0 ]; then
  echo -e "${GREEN}═══════════════════════════════════════${NC}"
  echo -e "${GREEN}  ✓ All lint gates passed${NC}"
  echo -e "${GREEN}═══════════════════════════════════════${NC}"
else
  echo -e "${RED}═══════════════════════════════════════${NC}"
  echo -e "${RED}  ✗ Lint gate failed — see errors above${NC}"
  echo -e "${RED}═══════════════════════════════════════${NC}"
  exit 1
fi

# Optional: run pytest smoke if --with-tests is passed and the API is reachable
if [ "${1:-}" = "--with-tests" ]; then
  echo ""
  echo -e "${YELLOW}[4/4] Backend pytest smoke (--with-tests)${NC}"
  if ! curl -fsS http://localhost:8001/docs > /dev/null 2>&1; then
    echo -e "${YELLOW}  ⚠ Skipped — no API at http://localhost:8001/docs${NC}"
    echo -e "${YELLOW}  Tip: ensure supervisor is running the backend.${NC}"
    exit 0
  fi
  cd backend
  if TEST_API_URL=http://localhost:8001 REACT_APP_BACKEND_URL=http://localhost:8001 \
     python -m pytest tests/test_smoke_recent_modules.py \
       -v --maxfail=5 --tb=short -p no:cacheprovider 2>&1; then
    echo -e "${GREEN}  ✓ Pytest smoke passed${NC}"
  else
    echo -e "${RED}  ✗ Pytest smoke failed${NC}"
    exit 1
  fi
  cd ..
fi

exit 0
p no:cacheprovider 2>&1; then
    echo -e "${GREEN}  ✓ Pytest smoke passed${NC}"
  else
    echo -e "${RED}  ✗ Pytest smoke failed${NC}"
    exit 1
  fi
  cd ..
fi

exit 0
