---
title: 1020 호남 문화소비 리서치 아카이브
created: 2026-10-01
tags: [아카이브, 리서치, 사용법]
---

# 1020 호남 문화소비 리서치 아카이브

전남·광주권 10~20대 문화 소비율·소비금액 리서치의 **원본 출처 + 검증 노트 + 분석**을 Obsidian 볼트로 정리한 폴더입니다.

## 내 Obsidian에 넣는 방법

### 방법 1 — 볼트가 git으로 동기화되는 경우 (권장)
```bash
cd /path/to/내-옵시디언-볼트
git remote add producer-han <이 레포 URL>   # 최초 1회
git fetch producer-han claude/zen-knuth-9j69f0
git checkout producer-han/claude/zen-knuth-9j69f0 -- obsidian
```

### 방법 2 — 폴더째 복사
```bash
git clone -b claude/zen-knuth-9j69f0 <이 레포 URL> /tmp/ph
cp -R /tmp/ph/obsidian "/path/to/내-옵시디언-볼트/1020-호남-문화소비"
```

## 원본 PDF 받기 (중요 — 반드시 로컬에서 실행)

이 세션은 클라우드 컨테이너에서 돌고 있고, **네트워크 정책이 `mcst.go.kr` · `kostat.go.kr` · `kosis.kr` · `kci.go.kr` · `kcti.re.kr` · `e-sir.org` 등 모든 국내 정부·학술 도메인을 403으로 차단**합니다. 그래서 PDF는 제가 받아둘 수 없었습니다.

대신 **한 줄로 전부 받는 스크립트**를 넣어뒀습니다. 사용자님 PC에서 실행하면 `_attachments/`에 전부 떨어집니다.

```bash
cd obsidian
bash scripts/download-sources.sh
```

실패한 항목은 `_attachments/_download-log.txt`에 남습니다. 정부 사이트는 세션 토큰을 요구하는 경우가 있어, 실패분은 `sources.csv`의 URL을 브라우저로 직접 열면 됩니다.

## 폴더 구조

| 폴더 | 내용 |
|---|---|
| `00-MOC/` | 전체 지도 (여기서 시작) |
| `10-원본통계/` | 정부 승인 통계 노트 |
| `20-보고서/` | 논문·연구보고서 노트 |
| `30-분석/` | 종합 분석 + 데이터 검증 |
| `_attachments/` | 다운로드된 PDF 보관 |
| `scripts/` | 일괄 다운로드 스크립트 |
| `sources.csv` | 전체 출처 URL 매니페스트 |

## 먼저 읽어야 할 것

> [!warning] Gemini가 준 수치 중 일부는 실제 통계와 불일치합니다
> 특히 **청년문화예술패스 지역별 수치는 어느 연도와도 맞지 않습니다.**
> 반드시 [[데이터 검증 노트]]를 먼저 읽고 쓰세요.

- [[1020 호남 문화소비 MOC]] — 전체 지도
- [[데이터 검증 노트]] — 무엇이 검증됐고 무엇이 틀렸는지
- [[전남광주 1020 소비 종합]] — 소비지수·금액·용돈 결론
