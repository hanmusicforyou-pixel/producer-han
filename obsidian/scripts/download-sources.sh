#!/usr/bin/env bash
#
# 1020 호남 문화소비 리서치 — 출처 일괄 다운로드
#
# ⚠️ 반드시 사용자님 로컬 PC에서 실행하세요.
#    클라우드 세션은 mcst.go.kr / kostat.go.kr / kosis.kr 등
#    국내 정부·학술 도메인이 전부 403으로 차단됩니다.
#
# 사용법:
#   cd obsidian
#   bash scripts/download-sources.sh
#
# 결과:
#   _attachments/            내려받은 파일
#   _attachments/_download-log.txt   성공/실패 기록

set -uo pipefail

# 한글 파일명 처리를 위해 UTF-8 로케일을 쓸 수 있으면 쓴다.
# (없어도 동작함 — 파일명 생성은 로케일에 의존하지 않도록 구현했다)
for _loc in C.UTF-8 en_US.UTF-8 ko_KR.UTF-8; do
  if locale -a 2>/dev/null | grep -qix "${_loc//./.}"; then
    export LC_ALL="$_loc"
    break
  fi
done
unset _loc

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CSV="$HERE/sources.csv"
OUT="$HERE/_attachments"
LOG="$OUT/_download-log.txt"

UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"

mkdir -p "$OUT"
: > "$LOG"

if [[ ! -f "$CSV" ]]; then
  echo "✗ sources.csv 를 찾을 수 없습니다: $CSV" >&2
  exit 1
fi

ok=0; fail=0; skip=0

log() { printf '%s\n' "$1" | tee -a "$LOG"; }

log "=== 다운로드 시작: $(date '+%Y-%m-%d %H:%M:%S') ==="
log ""

# CSV 1행(헤더) 건너뛰고 읽기. 마지막 필드(URL)에 콤마가 없다는 전제.
tail -n +2 "$CSV" | while IFS= read -r line; do
  [[ -z "${line// }" ]] && continue

  # 마지막 콤마 뒤 = URL, 첫 콤마 앞 = 분류
  url="${line##*,}"
  cat="${line%%,*}"
  # 제목 = 두 번째 필드
  rest="${line#*,}"
  title="${rest%%,*}"

  [[ "$url" != http* ]] && { skip=$((skip+1)); continue; }

  # 파일명 생성: 분류_제목 (특수문자 제거)
  # ★ 는 브래킷 없이 그대로 치환 (브래킷 표현식은 한글 바이트를 깨뜨림)
  safe="${cat}_${title}"
  safe="${safe//★/}"
  safe="$(printf '%s' "$safe" | tr '/\\:*?"<>|' '-' | sed -e 's/  */ /g' -e 's/^ //' -e 's/ $//')"
  safe="${safe:0:110}"

  # 확장자 추정
  case "$url" in
    *.pdf|*.PDF)        ext="pdf" ;;
    *boardDownload*)    ext="pdf" ;;
    *UplDownloadFile*)  ext="pdf" ;;
    *)                  ext="html" ;;
  esac

  dest="$OUT/${safe}.${ext}"

  if [[ -s "$dest" ]]; then
    log "- 이미 있음: ${safe}.${ext}"
    continue
  fi

  code="$(curl -sSL \
      --connect-timeout 20 --max-time 180 \
      --retry 3 --retry-delay 2 --retry-connrefused \
      -A "$UA" \
      -e "$url" \
      -o "$dest" \
      -w '%{http_code}' \
      "$url" 2>>"$LOG" || echo 000)"

  # --retry 는 시도마다 코드를 덧붙이므로 마지막 3자리만 쓴다
  code="${code: -3}"

  if [[ "$code" == "200" && -s "$dest" ]]; then
    size="$(wc -c < "$dest" | tr -d ' ')"
    # 실제로 PDF인지 확인 — 정부 사이트는 로그인 HTML을 PDF로 주는 경우가 있음
    if [[ "$ext" == "pdf" ]] && ! head -c 4 "$dest" | grep -q '%PDF'; then
      mv "$dest" "${dest%.pdf}.html"
      log "△ PDF 아님(HTML로 저장): ${safe}  [${size} bytes]  → 브라우저로 직접 받으세요"
      log "   $url"
    else
      log "✓ ${safe}.${ext}  [${size} bytes]"
    fi
    ok=$((ok+1))
  else
    rm -f "$dest"
    log "✗ 실패(HTTP $code): ${safe}"
    log "   $url"
    fail=$((fail+1))
  fi
done

log ""
log "=== 완료 ==="
log "저장 위치: $OUT"
log ""
log "※ 실패 항목은 위 로그의 URL을 브라우저로 직접 열어 받으세요."
log "   정부 사이트(mcst.go.kr, kostat.go.kr 등)는 세션 토큰을 요구해"
log "   curl 로는 받히지 않는 경우가 많습니다. 이건 정상입니다."
log ""
log "※ data.go.kr 원시데이터는 로그인·신청이 필요합니다:"
log "   https://www.data.go.kr/data/15119016/fileData.do"
log "   → 20대 장르별 관람률을 직접 집계하려면 이 파일이 반드시 필요합니다."

echo ""
echo "로그: $LOG"
