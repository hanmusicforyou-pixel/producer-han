#!/usr/bin/env python3
"""
공연 기획 간트차트 · Gemini 자동 보강 파이프라인
--------------------------------------------------
[공연 정보 + 기존 작업표] -> Gemini API -> 보강된 작업 JSON -> (Figma 렌더링에 사용)

사용법:
    export GEMINI_API_KEY=...        # 환경변수로 주입 (채팅/코드에 하드코딩 금지)
    python3 tools/gantt_gemini.py    # augmented_tasks.json 생성

출력: tools/augmented_tasks.json  (팀별 작업 목록. s/e 는 D-day, 음수=공연 전)
이 JSON 을 Claude 가 읽어 Figma use_figma 로 렌더링합니다.
"""
import os, json, sys, urllib.request

MODEL = "gemini-2.0-flash"  # 빠르고 무료 티어. 품질 우선이면 gemini-2.5-pro
API_KEY = os.environ.get("GEMINI_API_KEY")

# 현재 확정된 팀별 작업 (Figma 차트와 동일 소스)
CURRENT = {
  "경영팀": ["사전 예산 조직·편성 D-50","카드 포스기 수수료 확인 D-40","무대 설치 계약 D-30",
             "음향 오퍼 계약 D-30","매출 확인(법인계좌·카드사) D+1~D+3","아티스트 피 정산 안내 D+1",
             "무대·음향·외주사 정산 D+1~D+7"],
  "무대·음향팀": ["무대 음향팀 계약·도로 점용 허가 D-60","무대·음향 답사 D-55","무대 설치·안전 점검 D-1","무대 리허설 D-DAY"],
  "제작팀": ["안전관리규칙 매뉴얼 서면화 D-55","PA 소음 규제 확인 D-40","안전 홍보물·사이니지 제작 D-40","웹포스터·키비주얼 제작 D-20"],
  "MD팀": ["MD 컨텍·발주 D-40","부자재 발주 D-40","MD 보관 부킹 D-19","재고 잔여 수거 D-7","포스기 확인 D-5",
           "MD 발송 확인 D-3","MD 재고 확인 D-3","실시간 재고 파악 D-DAY","한정판매 프라이싱 D+3","온라인 한정판매 D+7"],
  "마케팅·홍보팀": ["지역신문 보도자료 D-14","충장로 SNS 홍보 D-7","아티스트 보도자료 D-4","홍보채널 전체 공지 D-2","마케팅 CX(인스타·X) D+1~D+3","온라인 MD 한정판매 홍보 D+7"],
  "PM·현장운영팀": ["스텝 고용·OT D-30","현장인력 1차 교육 D-30","현장인력 2차 교육 D-7","도로 점용 허가 재확인 D-5",
                    "대기열 관리·안전 D-DAY","퇴로 확보·안전(경찰협조) D-DAY","사후관리 회의 D+1","결과 보고서 작성 D+1~D+7"],
}

EVENT = {"기획": "이기한", "거점": "광주 충장로 우체국 앞", "형태": "K-POP 이머시브 팝업 (AR·MD·공연)"}

PROMPT = f"""너는 공연 프로덕션 PM 이다. 아래는 '{EVENT['형태']}' ({EVENT['거점']}) 의 팀별 운영 작업표다.
공연일을 D-DAY 로 하는 D-day 기준.

현재 작업표:
{json.dumps(CURRENT, ensure_ascii=False, indent=2)}

과제: 실제 로컬 팝업 운영에서 흔히 빠지는 작업을 팀별로 보강하라. 특히
- 인허가/안전/보험, 우천·전기 백업, 응급/소방 동선
- 접근성, 다국어 응대, 개인정보 동의, 정산 증빙
각 팀당 1~3개만 추가. 이미 있는 항목과 중복 금지.

반드시 아래 JSON 스키마로만 답하라(설명 금지):
{{"팀명": [{{"n":"작업명","o":"담당","s":시작Dday(정수,공연전=음수),"e":종료Dday(정수)}}]}}
"""

def call_gemini(prompt: str) -> str:
    if not API_KEY:
        sys.exit("ERROR: GEMINI_API_KEY 환경변수가 없습니다. 환경 설정에 추가 후 새 세션에서 실행하세요.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    return data["candidates"][0]["content"]["parts"][0]["text"]

if __name__ == "__main__":
    raw = call_gemini(PROMPT)
    added = json.loads(raw)
    out = os.path.join(os.path.dirname(__file__), "augmented_tasks.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(added, f, ensure_ascii=False, indent=2)
    n = sum(len(v) for v in added.values())
    print(f"OK · Gemini 가 {n}개 작업 보강 · {out}")
    print(json.dumps(added, ensure_ascii=False, indent=2))
