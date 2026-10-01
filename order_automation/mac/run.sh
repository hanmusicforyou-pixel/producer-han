#!/bin/bash
# 가상환경을 자동으로 쓰는 실행 도우미.  예)  bash mac/run.sh test-login   /   bash mac/run.sh run
cd "$(dirname "$0")/.." || exit 1
[ -x .venv/bin/python ] || { echo "먼저 'bash mac/setup_mac.sh' 를 실행하세요."; exit 1; }
exec .venv/bin/python main.py "$@"
