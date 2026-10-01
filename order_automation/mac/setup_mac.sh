#!/bin/bash
# 영암부부농원 발주 자동화 - Mac 최초 설치 (한 번만 실행)
#   터미널에서:  bash mac/setup_mac.sh      (order_automation 폴더 안에서)
set -e
cd "$(dirname "$0")/.."
APP_DIR="$(pwd)"

say() { printf '\n\033[1m%s\033[0m\n' "$1"; }
fail() { printf '\n\033[31m✖ %s\033[0m\n' "$1"; exit 1; }

say "1/5  Python 확인"
if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 가 없습니다. 터미널에서 'xcode-select --install' 을 실행해 설치한 뒤 다시 실행하세요. (또는 https://www.python.org/downloads/ 에서 설치)"
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  fail "Python 3.9 이상이 필요합니다 (현재: $(python3 --version)). https://www.python.org/downloads/ 에서 최신 버전을 설치한 뒤 다시 실행하세요."
fi
echo "✔ $(python3 --version)"

case "$APP_DIR" in
  "$HOME/Documents"*|"$HOME/Desktop"*|"$HOME/Downloads"*|"$HOME/Library/Mobile Documents"*)
    echo "⚠ 이 폴더($APP_DIR)는 macOS 보호 폴더 안에 있습니다."
    echo "  자동 실행(백그라운드)이 파일을 못 읽을 수 있으니 홈 폴더(~)로 옮기는 것을 권장합니다:"
    echo "    cd ~ && git clone https://github.com/hanmusicforyou-pixel/producer-han.git"
    ;;
esac

say "2/5  가상환경(.venv) 만들고 패키지 설치"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
echo "✔ 설치 완료"

say "3/5  설정 파일(.env) 만들기"
[ -f .env ] || cp .env.example .env
chmod 600 .env
ask() {  # ask KEY "질문" [기본값]
  local cur=""; local ans
  read -r -p "$2 ${3:+[$3] }: " ans
  ans="${ans:-$3}"
  [ -n "$ans" ] && ENV_VALUE="$ans" .venv/bin/python mac/set_env.py "$1"
  return 0
}
ask MY_NAME  "안내문 서명에 쓸 내 이름"
ask MY_PHONE "안내문 서명에 쓸 내 연락처 (예 010-1234-5678)"
ask NAVER_ID "네이버 아이디" "k333896"
printf '네이버 비밀번호 (화면에 표시되지 않음. 2단계 인증 사용 시 애플리케이션 비밀번호): '
read -r -s NAVER_PW; echo
[ -n "$NAVER_PW" ] || fail "비밀번호가 비어 있습니다. 다시 실행해 주세요."
ENV_VALUE="$NAVER_PW" .venv/bin/python mac/set_env.py NAVER_APP_PASSWORD
unset NAVER_PW
echo "✔ .env 저장 (본인만 읽을 수 있게 권한 600)"

say "4/5  네이버 로그인 테스트"
if [ "${SKIP_LOGIN_TEST:-0}" = "1" ]; then
  echo "(건너뜀)"
elif .venv/bin/python main.py test-login; then
  echo "✔ 로그인 성공"
else
  cat <<'MSG'

✖ 로그인에 실패했습니다. 아래 순서로 확인한 뒤 'bash mac/setup_mac.sh' 를 다시 실행하세요.
  1) 네이버 메일 > 환경설정 > POP3/IMAP 설정 > IMAP/SMTP 설정 탭 > '사용함' 저장
  2) 2단계 인증을 쓰면 일반 비밀번호는 거부됩니다 → 네이버 보안설정에서 '애플리케이션 비밀번호' 발급
  3) 오류 문구가 'check your username, password' 면 비밀번호 문제, 'IMAP/SMTP settings' 면 1번 문제
MSG
  exit 1
fi

say "5/5  완료"
cat <<MSG
다음 단계:
  - 매일 자동 실행 등록:   bash mac/install_schedule.sh
  - 지금 한 번 수동 실행:  bash mac/run.sh run --dry-run     (실제 발송 없이 테스트)
  - 전체 흐름 시연:        bash mac/run.sh demo              (네이버 접속 없이)
MSG
