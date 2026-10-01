#!/bin/bash
# 매일 한국시간 10:00~20:30, 30분마다 'python main.py run' 을 자동 실행하도록 macOS launchd 에 등록합니다.
#   등록:  bash mac/install_schedule.sh        해제: bash mac/uninstall_schedule.sh
set -e
cd "$(dirname "$0")/.."
APP_DIR="$(pwd)"
LABEL="com.producerhan.yeongam-order"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
[ -x .venv/bin/python ] || { echo "먼저 'bash mac/setup_mac.sh' 를 실행하세요."; exit 1; }
[ -f .env ] || { echo ".env 가 없습니다. 먼저 'bash mac/setup_mac.sh' 를 실행하세요."; exit 1; }
mkdir -p "$HOME/Library/LaunchAgents" data/logs

# plist 는 파이썬으로 생성 (경로에 공백이 있어도 안전)
APP_DIR="$APP_DIR" LABEL="$LABEL" PLIST="$PLIST" .venv/bin/python - <<'PY'
import os, plistlib
app = os.environ["APP_DIR"]
slots = [{"Hour": h, "Minute": m} for h in range(10, 21) for m in (0, 30)]
data = {
    "Label": os.environ["LABEL"],
    "ProgramArguments": [f"{app}/.venv/bin/python", f"{app}/main.py", "run"],
    "WorkingDirectory": app,
    "StartCalendarInterval": slots,
    "StandardOutPath": f"{app}/data/logs/launchd.log",
    "StandardErrorPath": f"{app}/data/logs/launchd.log",
    "EnvironmentVariables": {"PYTHONUNBUFFERED": "1", "TZ": "Asia/Seoul"},
}
with open(os.environ["PLIST"], "wb") as f:
    plistlib.dump(data, f)
PY
plutil -lint "$PLIST" >/dev/null

UIDN="$(id -u)"
launchctl bootout "gui/$UIDN" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UIDN" "$PLIST"
launchctl enable "gui/$UIDN/$LABEL"

echo "✔ 자동 실행 등록 완료: 매일 10:00~20:30 사이 30분마다 (한국시간)"
echo "  - 설정 파일: $PLIST"
echo "  - 실행 기록: $APP_DIR/data/logs/launchd.log"
echo "  - 맥이 잠자기 상태여도 깨어나는 즉시 놓친 실행을 한 번 수행합니다. 완전히 꺼져 있으면 실행되지 않습니다."
echo "  - 운영 종료일(기본 2026-10-30) 이후에는 실행돼도 아무 것도 하지 않습니다."

printf '\n매일 09:55 에 맥이 자동으로 켜지거나 깨어나게 할까요? (관리자 암호 필요) [y/N]: '
read -r ans
if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
  sudo pmset repeat wakeorpoweron MTWRFSU 09:55:00 && echo "✔ 매일 09:55 자동 켜짐/깨어남 설정 (해제: sudo pmset repeat cancel)"
fi
echo
echo "참고: 노트북은 전원 어댑터를 연결하고 뚜껑을 열어 두세요 (덮개를 닫으면 대부분 잠자기 상태)."
