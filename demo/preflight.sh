#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# demo/preflight.sh — Preflight validation for CrashTest demo
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

echo "============================================================"
echo "  CRASHTEST PREFLIGHT VERIFICATION"
echo "============================================================"

# 1. Check Package Installed
if command -v crashtest >/dev/null 2>&1; then
    echo "[PASS] Package installed (crashtest CLI available)"
else
    echo "[FAIL] Package not installed. Run 'pip install -e .' first."
    exit 1
fi

# 2. Check Cassettes Present
python3 -c "
from crashtest import store
ids = store.list_cassettes()
required = {'sc-01', 'sc-02', 'b-01', 'b-02'}
missing = required - set(ids)
if missing:
    print(f'[FAIL] Missing cassettes: {missing}')
    exit(1)
print('[PASS] Cassettes present (sc-01, sc-02, b-01, b-02)')
"

# 3. Check Frozen Replay Correctness
python3 -c "
from crashtest import store, replay
sc01 = store.load('sc-01')
b01 = store.load('b-01')

r_sc01 = replay.frozen(sc01, runs=1)
r_b01 = replay.frozen(b01, runs=1)

if 'CRASH' in r_sc01.verdicts and 'PASS' in r_b01.verdicts:
    print('[PASS] Frozen replay correct (sc-01 CRASH, b-01 PASS)')
else:
    print(f'[FAIL] Frozen replay unexpected output: sc-01={r_sc01.verdicts}, b-01={r_b01.verdicts}')
    exit(1)
"

# 4. Check API & UI serving
python3 -c "
from fastapi.testclient import TestClient
from crashtest.api import app

client = TestClient(app)

h = client.get('/api/health')
if h.status_code != 200 or not h.json().get('ok'):
    print('[FAIL] API health check failed')
    exit(1)
print('[PASS] API health endpoint (HTTP 200, offline ready)')

u = client.get('/')
if u.status_code != 200:
    print('[FAIL] UI root endpoint failed')
    exit(1)
print('[PASS] UI static index (HTTP 200, flight recorder loaded)')
"

# 5. Check Pytest Suite
if pytest -q >/dev/null 2>&1; then
    echo "[PASS] Pytest suite (all tests green offline)"
else
    echo "[FAIL] Pytest suite failed"
    exit 1
fi

echo "============================================================"
echo "  ALL PREFLIGHT CHECKS PASSED — READY FOR DEMO"
echo "============================================================"
