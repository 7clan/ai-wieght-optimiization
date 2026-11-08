#!/bin/bash
# Final frozen validation sequence — Session 035 (TRUSTED-SCAFFOLD).
# Runs the complete acceptance battery in order and records raw evidence:
#   1. apitest phase pre      (16 checks; wipes and re-seeds)
#   2. dev-server RESTART     (persistence requirement)
#   3. apitest post-restart   (2 checks)
#   4. uitest                 (20 checks + page-error count)
#   5. visual evaluator       (10 metrics x 3 viewports)
#   6. real screenshots       (1440x900, 390x844, 320x700 + empty state)
set -u
EXP=/home/z/s035/experiments/zai-fullstack
NODE_ENV_EXPORT="PATH=/home/z/.npm-global/bin:/usr/local/bin:/usr/bin:/bin NODE_PATH=/home/z/.npm-global/lib/node_modules BASE=http://127.0.0.1:3000"
VENV=/home/z/.venv/bin/python3
DAEMON=/home/z/s035/archagent/fullstack/daemonize.py
OUT=$EXP/reports

echo "=== [1/6] apitest pre-restart ==="
env $NODE_ENV_EXPORT node $EXP/apitest.mjs --phase pre 2>&1 | tee $OUT/apitest-pre.txt | tail -4
PRE=$?

echo "=== [2/6] dev-server restart (persistence) ==="
pkill -f "next dev -p 3000"; pkill -f "next-server"; sleep 4
$VENV $DAEMON /home/z/my-project/dev.log -- bash -c 'cd /home/z/my-project && exec node_modules/.bin/next dev -p 3000 >> dev.log 2>&1'
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/ --max-time 5)
  [ "$code" = "200" ] && break
  sleep 2
done
echo "dev restarted: HTTP $code after restart"

echo "=== [3/6] apitest post-restart ==="
env $NODE_ENV_EXPORT node $EXP/apitest.mjs --phase post-restart 2>&1 | tee $OUT/apitest-post.txt | tail -4
POST=$?

echo "=== [4/6] uitest (20 checks) ==="
env $NODE_ENV_EXPORT node $EXP/uitest.mjs 2>&1 | tee $OUT/uitest.txt | tail -6
UI=$?

echo "=== [5/6] visual evaluator (10 metrics x 3 viewports) ==="
cd /home/z/s035
env $NODE_ENV_EXPORT node archagent/visual/evaluator.mjs \
  --base http://127.0.0.1:3000/ \
  --out $OUT/visual-final.json \
  --waitfor "h1" \
  --viewports "1440x900,390x844,320x700" 2>&1 | tail -8
EV=$?

echo "=== [6/6] screenshots ==="
env $NODE_ENV_EXPORT node $EXP/shots.mjs --out $EXP/shots 2>&1 | tail -6
SH=$?

echo ""
echo "=== VALIDATION SUMMARY ==="
echo "apitest pre-restart : exit $PRE"
echo "apitest post-restart: exit $POST"
echo "uitest              : exit $UI"
echo "visual evaluator    : exit $EV"
echo "screenshots         : exit $SH"
grep -h "checks passed\|pageErrors" $OUT/apitest-pre.txt $OUT/apitest-post.txt $OUT/uitest.txt 2>/dev/null
