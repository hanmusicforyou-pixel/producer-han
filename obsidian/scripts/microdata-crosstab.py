#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국민문화예술활동조사 원시데이터 → 지역규모 × 연령대 교차집계

목적
----
보도로만 확인된 "가까운 곳에 시설이 없다 12.4%" 를
  ① 조사 연도 확정
  ② 지역규모(대도시/중소도시/읍면) × 연령대 교차표
로 직접 집계한다. 전국 12.4% 가 '읍면 × 10~20대' 에서 몇 %인지가 목표.

사용법
------
  # 1단계 — 파일 구조 파악 (컬럼명·값라벨 출력)
  python3 scripts/microdata-crosstab.py --inspect

  # 2단계 — 교차집계 (컬럼 자동탐지 시도)
  python3 scripts/microdata-crosstab.py

  # 컬럼을 직접 지정
  python3 scripts/microdata-crosstab.py \
      --region-col 지역규모 --age-col 연령 --barrier-col 저해요인1

원시데이터 받는 곳
-----------------
  https://www.data.go.kr/data/15119016/fileData.do
  (로그인·신청이 필요할 수 있다. 받은 파일을 _attachments/ 에 두면 자동으로 찾는다)

의존성: pandas, pyreadstat(.sav), openpyxl(.xlsx)
"""

import argparse
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ATTACH = HERE / "_attachments"
OUT = HERE / "30-분석"

# 컬럼 자동탐지 키워드 (우선순위 순)
REGION_KEYS = ["지역규모", "도시규모", "동읍면", "읍면", "권역규모", "city_size", "DO_EUP"]
AGE_KEYS = ["연령대", "만연령", "연령", "나이", "age", "AGE"]
BARRIER_KEYS = ["저해", "장애요인", "어려운점", "불만", "미관람", "관람하지"]
FACILITY_HINT = ["가까운", "시설이 없", "시설 없", "거리", "접근"]


def find_data_files():
    """_attachments/ 에서 데이터 파일 후보를 찾는다. zip 은 풀어서 본다."""
    if not ATTACH.exists():
        return []
    exts = {".sav", ".csv", ".xlsx", ".xls", ".dta", ".txt"}
    found = [p for p in ATTACH.rglob("*") if p.suffix.lower() in exts and p.is_file()]

    # zip 안쪽도 본다
    for z in ATTACH.rglob("*.zip"):
        dest = ATTACH / (z.stem + "_unzipped")
        if not dest.exists():
            try:
                with zipfile.ZipFile(z) as zf:
                    zf.extractall(dest)
                print(f"  압축 해제: {z.name} → {dest.name}/")
            except Exception as e:
                print(f"  압축 해제 실패 {z.name}: {e}")
        found += [p for p in dest.rglob("*") if p.suffix.lower() in exts and p.is_file()]

    # 큰 파일 우선 (원시데이터는 보통 크다)
    return sorted(set(found), key=lambda p: -p.stat().st_size)


def load(path):
    """데이터 파일을 (DataFrame, value_labels dict) 로 읽는다."""
    import pandas as pd

    suf = path.suffix.lower()
    labels = {}

    if suf == ".sav":
        import pyreadstat
        df, meta = pyreadstat.read_sav(str(path), apply_value_formats=False)
        labels = dict(meta.variable_value_labels or {})
        # 변수 설명도 같이 보관
        df.attrs["column_labels"] = dict(zip(meta.column_names, meta.column_labels or []))
        return df, labels

    if suf in (".xlsx", ".xls"):
        return pd.read_excel(path), labels

    # csv / txt — 한글 인코딩 순차 시도
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        for sep in (",", "\t", "|"):
            try:
                df = pd.read_csv(path, encoding=enc, sep=sep, low_memory=False)
                if df.shape[1] > 1:
                    print(f"  읽음: encoding={enc}, sep={sep!r}")
                    return df, labels
            except Exception:
                continue
    raise RuntimeError(f"읽을 수 없음: {path}")


def pick(cols, keys):
    """키워드로 컬럼 후보를 찾는다."""
    hits = []
    for k in keys:
        for c in cols:
            if k.lower() in str(c).lower() and c not in hits:
                hits.append(c)
    return hits


def inspect(df, labels):
    print(f"\n{'='*70}\n행 {len(df):,} · 열 {df.shape[1]}\n{'='*70}")

    collabels = df.attrs.get("column_labels", {})
    print("\n--- 전체 컬럼 ---")
    for c in df.columns:
        desc = collabels.get(c, "")
        nuniq = df[c].nunique(dropna=True)
        extra = f"  ← {desc}" if desc else ""
        print(f"  {str(c):<24} uniq={nuniq:<6}{extra}")

    for name, keys in (("지역규모", REGION_KEYS), ("연령", AGE_KEYS), ("저해요인", BARRIER_KEYS)):
        cand = pick(df.columns, keys)
        print(f"\n--- '{name}' 후보: {cand if cand else '없음'} ---")
        for c in cand[:6]:
            vc = df[c].value_counts(dropna=False).head(12)
            lab = labels.get(c, {})
            for v, n in vc.items():
                tag = f" ({lab.get(v)})" if lab and v in lab else ""
                print(f"    {c} = {v}{tag}: {n:,}")
            print()

    # '가까운 곳에 시설' 라벨을 가진 변수 전수 탐색
    print("--- 값라벨에 '가까운/시설없음/거리' 포함된 변수 ---")
    any_hit = False
    for var, lab in labels.items():
        for code, text in lab.items():
            if any(h in str(text) for h in FACILITY_HINT):
                print(f"    {var} = {code} : {text}")
                any_hit = True
    if not any_hit:
        print("    없음 (.sav 가 아니거나 라벨 미포함 — 코드북 PDF 확인 필요)")


def age_bucket(v):
    """연령 값을 10대/20대/… 로 묶는다. 이미 구간코드면 그대로 둔다."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return v
    if n != n:  # NaN
        return v
    if n > 100:  # 코드값으로 보임
        return v
    if n < 15:
        return "15세미만"
    if n < 20:
        return "10대(15-19)"
    if n < 30:
        return "20대"
    if n < 40:
        return "30대"
    if n < 50:
        return "40대"
    if n < 60:
        return "50대"
    if n < 70:
        return "60대"
    return "70세+"


def crosstab(df, labels, region_col, age_col, barrier_col, weight_col=None):
    import pandas as pd

    d = df[[region_col, age_col, barrier_col] + ([weight_col] if weight_col else [])].copy()

    # 라벨 적용
    for c in (region_col, barrier_col):
        if c in labels:
            d[c] = d[c].map(labels[c]).fillna(d[c])
    d["연령대"] = d[age_col].map(age_bucket)

    # '가까운 곳에 시설이 없다' 응답 플래그
    def is_facility(v):
        return any(h in str(v) for h in FACILITY_HINT)

    d["시설없음"] = d[barrier_col].map(is_facility)

    w = d[weight_col] if weight_col else None
    if w is not None:
        num = d[d["시설없음"]].groupby([region_col, "연령대"])[weight_col].sum()
        den = d.groupby([region_col, "연령대"])[weight_col].sum()
    else:
        num = d[d["시설없음"]].groupby([region_col, "연령대"]).size()
        den = d.groupby([region_col, "연령대"]).size()

    pct = (num / den * 100).round(1).unstack()
    n = den.unstack()

    print("\n" + "=" * 70)
    print(f"'가까운 곳에 시설이 없다' 응답률 (%)   가중치: {weight_col or '없음(단순집계)'}")
    print("=" * 70)
    print(pct.to_string())
    print("\n--- 응답자 수(분모) ---")
    print(n.to_string())

    # 전체 비율 (보도의 12.4% 와 대조)
    tot_num = d[d["시설없음"]][weight_col].sum() if weight_col else d["시설없음"].sum()
    tot_den = d[weight_col].sum() if weight_col else len(d)
    print(f"\n전체: {tot_num/tot_den*100:.1f}%   ← 보도 수치 12.4% 와 대조")

    # 마크다운 저장
    OUT.mkdir(exist_ok=True)
    md = OUT / "원시데이터 교차집계.md"
    with open(md, "w", encoding="utf-8") as f:
        f.write("---\ntitle: 원시데이터 교차집계\ntags: [분석, 원시데이터, 교차집계, 접근성]\n")
        f.write('up: "[[1020 호남 문화소비 MOC]]"\n신뢰도: A\n---\n\n')
        f.write("# 원시데이터 교차집계 — 지역규모 × 연령대\n\n")
        f.write("문화체육관광부 「국민문화예술활동조사」 원시데이터 직접 집계.\n")
        f.write("보도 경유 수치(신뢰도 B)가 아니라 **1차 집계(신뢰도 A)** 다.\n\n")
        f.write(f"- 사용 컬럼: 지역규모=`{region_col}` · 연령=`{age_col}` · 저해요인=`{barrier_col}`\n")
        f.write(f"- 가중치: {weight_col or '없음 (단순집계)'}\n")
        f.write(f"- 전체 응답률: **{tot_num/tot_den*100:.1f}%** (보도 수치 12.4% 와 대조)\n\n")
        f.write("## '가까운 곳에 시설이 없다' 응답률 (%)\n\n")
        f.write(pct.to_markdown() + "\n\n")
        f.write("*출처: 문화체육관광부 「국민문화예술활동조사」 원시데이터 ")
        f.write("([공공데이터포털](https://www.data.go.kr/data/15119016/fileData.do)) 직접 집계 · 신뢰도 A*\n\n")
        f.write("## 응답자 수 (분모)\n\n")
        f.write(n.to_markdown() + "\n\n")
        f.write("*분모가 30 미만인 칸은 해석하지 말 것 — 표본오차가 과대하다.*\n\n")
        f.write("## 관련 노트\n[[거리 접근성 제약]] · [[데이터 검증 노트]] · [[전남광주 1020 소비 종합]]\n")
    print(f"\n저장: {md}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="데이터 파일 경로 (생략하면 _attachments/ 에서 자동 탐색)")
    ap.add_argument("--inspect", action="store_true", help="구조만 출력하고 종료")
    ap.add_argument("--region-col")
    ap.add_argument("--age-col")
    ap.add_argument("--barrier-col")
    ap.add_argument("--weight-col", help="가중치 변수 (있으면 반드시 지정 — 없으면 단순집계)")
    a = ap.parse_args()

    if a.file:
        path = Path(a.file)
    else:
        cands = find_data_files()
        if not cands:
            print("데이터 파일을 찾지 못했습니다.\n")
            print("  1) https://www.data.go.kr/data/15119016/fileData.do 에서 원시데이터를 받아")
            print(f"  2) {ATTACH}/ 에 넣고")
            print("  3) python3 scripts/microdata-crosstab.py --inspect")
            sys.exit(1)
        print("찾은 파일:")
        for p in cands[:8]:
            print(f"  {p.stat().st_size/1e6:8.1f}MB  {p.relative_to(HERE)}")
        path = cands[0]
        print(f"\n사용: {path.name}")

    df, labels = load(path)

    if a.inspect or not (a.region_col and a.age_col and a.barrier_col):
        inspect(df, labels)
        if not a.inspect:
            print("\n" + "!" * 70)
            print("컬럼 자동탐지로는 확정할 수 없습니다. 위 출력을 보고 지정하세요:")
            print("  python3 scripts/microdata-crosstab.py \\")
            print("      --region-col <지역규모> --age-col <연령> --barrier-col <저해요인> \\")
            print("      --weight-col <가중치>")
            print("!" * 70)
        return

    crosstab(df, labels, a.region_col, a.age_col, a.barrier_col, a.weight_col)


if __name__ == "__main__":
    main()
