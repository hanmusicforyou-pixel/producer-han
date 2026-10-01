"""발주서 엑셀 읽기/쓰기.

업로드된 양식(13열) 기준:
받는분성함 | 받는분우편번호 | 받는분주소(전체, 분할) | 받는분전화번호 | 받는분기타연락처 | 박스수량 |
배송메세지1 | 품목명 | 보내는분성명 | 보내는분전화번호 | 보내는분주소(전체, 분할) | 운송장번호 | 원본품목(요약용)
"""
from __future__ import annotations

import csv
import io
import logging
import re
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

log = logging.getLogger(__name__)

COLUMNS = [
    "받는분성함", "받는분우편번호", "받는분주소(전체, 분할)", "받는분전화번호", "받는분기타연락처",
    "박스수량", "배송메세지1", "품목명", "보내는분성명", "보내는분전화번호",
    "보내는분주소(전체, 분할)", "운송장번호", "원본품목(요약용)",
]
COL_WIDTHS = {"A": 10, "B": 10, "C": 46, "D": 14, "E": 12, "F": 8, "G": 10, "H": 18, "I": 10, "J": 14, "K": 22, "L": 16, "M": 16}

# 헤더 별칭 (공백 제거, 괄호 앞부분 기준으로 비교)
ALIASES: dict[str, list[str]] = {
    "받는분성함": ["받는분성함", "받는분이름", "받는분", "받는분명", "수령인", "수령인명", "수취인", "수취인명", "받는사람", "고객명", "주문자", "수하인", "수하인명", "수하인이름"],
    "받는분우편번호": ["받는분우편번호", "우편번호", "수령인우편번호"],
    "받는분주소(전체, 분할)": ["받는분주소", "주소", "수령인주소", "수취인주소", "배송주소", "배송지", "받는분주소전체", "수하인주소"],
    "받는분전화번호": ["받는분전화번호", "받는분연락처", "받는분휴대폰", "전화번호", "연락처", "휴대폰", "수령인전화번호", "수령인연락처", "수취인전화번호", "수취인연락처", "수하인전화", "수하인전화번호", "수하인연락처"],
    "받는분기타연락처": ["받는분기타연락처", "기타연락처", "전화번호2", "연락처2", "받는분전화번호2"],
    "박스수량": ["박스수량", "수량", "박스", "개수", "갯수", "주문수량", "박스개수"],
    "배송메세지1": ["배송메세지1", "배송메세지", "배송메시지", "배송요청사항", "요청사항", "배송메모", "메세지", "메시지"],
    "품목명": ["품목명", "상품명", "품목", "상품", "옵션", "상품옵션", "옵션명", "제품명", "물품명", "물품"],
    "보내는분성명": ["보내는분성명", "보내는분", "보내는분이름", "발송인", "발송인명", "보내는사람", "업체명", "판매자", "판매자명"],
    "보내는분전화번호": ["보내는분전화번호", "보내는분연락처", "발송인전화번호", "발송인연락처", "업체전화번호"],
    "보내는분주소(전체, 분할)": ["보내는분주소", "발송인주소", "업체주소"],
    "운송장번호": ["운송장번호", "송장번호", "운송장", "송장", "택배번호"],
    "원본품목(요약용)": ["원본품목", "원본품목요약용", "요약품목", "품목요약", "집계품목"],
}
_ALIAS_LOOKUP: dict[str, str] = {}
for canon, names in ALIASES.items():
    for n in names:
        _ALIAS_LOOKUP[n] = canon

REQUIRED_FOR_HEADER = {"받는분성함", "품목명"}
YELLOW = PatternFill("solid", fgColor="FFFFFF00")
GREY = PatternFill("solid", fgColor="FFD9D9D9")
GREEN = PatternFill("solid", fgColor="FFE2EFDA")
THIN = Side(style="thin", color="FF999999")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
BOLD = Font(bold=True)
CENTER = Alignment(horizontal="center", vertical="center")


def _norm_header(v: Any) -> str:
    s = str(v or "").strip()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[\(\[（【].*$", "", s)  # 괄호 이후 제거: 받는분주소(전체, 분할) → 받는분주소
    s = s.replace("*", "").replace("※", "")
    return s


def canonical_header(v: Any) -> str | None:
    n = _norm_header(v)
    if not n:
        return None
    if n in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[n]
    # 부분 일치 (예: '받는분성함(필수)' 는 위에서 괄호 제거되어 처리됨, '받는 분 전화' 등)
    for alias, canon in _ALIAS_LOOKUP.items():
        if len(alias) >= 4 and (alias in n or n in alias):
            return canon
    return None


def clean_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return "" if s.lower() in ("none", "nan") else s


def clean_phone(v: Any) -> str:
    s = clean_str(v)
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    if s.isdigit() and len(digits) in (9, 10) and not digits.startswith("0"):
        return "0" + digits  # 엑셀이 숫자로 저장해 앞 0 이 사라진 경우 복원
    return s


def clean_postal(v: Any) -> str:
    s = clean_str(v)
    if s.isdigit() and len(s) < 5:
        return s.zfill(5)
    return s


_REGION = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주",
    "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기", "강원도": "강원",
    "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북",
    "전라남도": "전남", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "전남광주통합특별시": "광주",
}


def addr_prefix(addr: str, tokens: int = 3) -> str:
    """주소 앞부분(시도 시군구 읍면동/도로)만 정규화해 비교용으로 반환. '****' 가림과 시도 표기 차이를 흡수."""
    parts = re.sub(r"[\*\(\)\[\],]", " ", clean_str(addr)).split()
    parts = [_REGION.get(p, p) for p in parts]
    return "".join(parts[:tokens])


def _masked(v: Any) -> bool:
    return "*" in clean_str(v)


def clean_qty(v: Any) -> int:
    s = clean_str(v)
    if not s:
        return 1
    m = re.search(r"\d+", s.replace(",", ""))
    return int(m.group()) if m else 1


_WEIGHT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|㎏|g|KG|Kg|G)", re.IGNORECASE)
_ITEM_RE = re.compile(r"^\s*(\d+)\s*(?:개|박스|box|BOX|ea|EA)?\s*[,/]?\s*(\d+(?:\.\d+)?\s*(?:kg|㎏|g))\s+(.+?)\s*$", re.IGNORECASE)


def weight_kg(text: str) -> float | None:
    m = _WEIGHT_RE.search(text or "")
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2).lower()
    return num / 1000 if unit == "g" else num


def product_key(item_name: str, summary_name: str = "") -> str:
    """'1개 1kg  청무화과' → '청무화과 1kg'. 원본품목(요약용) 값이 있으면 그걸 우선 사용."""
    s = re.sub(r"\s+", " ", (summary_name or "").strip())
    if s:
        return s
    raw = re.sub(r"\s+", " ", (item_name or "").strip())
    m = _ITEM_RE.match(raw)
    if m:
        weight = re.sub(r"\s+", "", m.group(2)).replace("㎏", "kg").lower()
        return f"{m.group(3).strip()} {weight}"
    return raw


def product_sort_key(key: str) -> tuple:
    w = weight_kg(key)
    name = _WEIGHT_RE.sub("", key).strip()
    return (name, w if w is not None else 9999, key)


@dataclass
class OrderRow:
    values: dict[str, Any]              # 13열 값
    vendor_email: str = ""
    vendor_name: str = ""
    source_file: str = ""
    source_row: int = 0
    changed: dict[str, tuple[Any, Any]] = field(default_factory=dict)  # 회신에서 바뀐 값 (전, 후)

    def __getitem__(self, k: str) -> Any:
        return self.values.get(k, "")

    @property
    def qty(self) -> int:
        return clean_qty(self.values.get("박스수량"))

    @property
    def product(self) -> str:
        return product_key(clean_str(self.values.get("품목명")), clean_str(self.values.get("원본품목(요약용)")))

    @property
    def tracking(self) -> str:
        return clean_str(self.values.get("운송장번호"))

    @property
    def missing_fields(self) -> list[str]:
        out = []
        for k in ("받는분성함", "받는분주소(전체, 분할)", "받는분전화번호", "품목명"):
            if not clean_str(self.values.get(k)):
                out.append(k)
        return out

    def match_keys(self) -> list[tuple]:
        """엄격 → 느슨 순서의 매칭 키. 값이 비면(전화가 가려진 경우 등) 해당 단계는 건너뜀."""
        name = re.sub(r"\s+", "", clean_str(self["받는분성함"]))
        raw_phone = clean_str(self["받는분전화번호"])
        phone = "" if _masked(raw_phone) else re.sub(r"\D", "", raw_phone)
        item = re.sub(r"\s+", "", self.product)
        a3 = addr_prefix(clean_str(self["받는분주소(전체, 분할)"]), 3)
        a2 = addr_prefix(clean_str(self["받는분주소(전체, 분할)"]), 2)
        return [(name, phone, item), (name, a3, item), (name, phone), (name, a3), (name, item), (name, a2), (name,)]

    def dedup_key(self) -> tuple:
        return tuple(clean_str(self.values.get(c)) for c in COLUMNS)


# ── 읽기 ────────────────────────────────────────────────────────────────
def _row_mapping(cells: list[Any]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for ci, v in enumerate(cells):
        canon = canonical_header(v)
        if canon and canon not in mapping.values():
            mapping[ci] = canon
    return mapping


def _combine_header_rows(top: list[Any], bottom: list[Any]) -> list[str]:
    """두 줄 헤더를 한 줄로 합침. 병합 셀(윗줄이 비어 있음)은 왼쪽 값을 이어받음.
    예) 윗줄 [운송장번호, 수하인, -, -] + 아랫줄 [-, 이름, 주소, 전화] → [운송장번호, 수하인이름, 수하인주소, 수하인전화]
    """
    n = max(len(top), len(bottom))
    out: list[str] = []
    last_top = ""
    for ci in range(n):
        t = clean_str(top[ci]) if ci < len(top) else ""
        b = clean_str(bottom[ci]) if ci < len(bottom) else ""
        if t:
            last_top = t
        elif not b:
            last_top = ""  # 아랫줄도 비어 있으면 병합 구간 끝
        out.append(f"{t or (last_top if b else '')}{b}")
    return out


def _detect_header(rows: list[list[Any]]) -> tuple[int, dict[int, str]] | None:
    """(데이터 시작 행 인덱스, {열번호: 표준 헤더}) 반환. 한 줄 헤더와 두 줄 헤더를 모두 시도해 더 많이 인식된 쪽 선택."""
    best: tuple[int, dict[int, str]] | None = None
    limit = min(20, len(rows))
    for idx in range(limit):
        candidates = [(idx + 1, _row_mapping(rows[idx]))]
        if idx + 1 < len(rows):
            candidates.append((idx + 2, _row_mapping(_combine_header_rows(rows[idx], rows[idx + 1]))))
        for start, mapping in candidates:
            found = set(mapping.values())
            if len(found) >= 3 and REQUIRED_FOR_HEADER <= found:
                if best is None or len(mapping) > len(best[1]):
                    best = (start, mapping)
    return best


def _rows_to_orders(rows: list[list[Any]], filename: str, sheet: str) -> list[OrderRow]:
    detected = _detect_header(rows)
    if not detected:
        log.debug("발주 헤더 없는 시트 건너뜀: %s [%s]", filename, sheet)
        return []
    start, mapping = detected
    out: list[OrderRow] = []
    for rno, row in enumerate(rows[start:], start=start + 1):
        vals: dict[str, Any] = {c: "" for c in COLUMNS}
        for ci, canon in mapping.items():
            if ci < len(row):
                vals[canon] = row[ci]
        first = clean_str(row[0]) if row else ""
        if first.startswith(("※", "합계", "총", "#")):
            continue
        if not clean_str(vals["받는분성함"]) and not clean_str(vals["품목명"]):
            continue
        vals["받는분성함"] = clean_str(vals["받는분성함"])
        vals["받는분우편번호"] = clean_postal(vals["받는분우편번호"])
        vals["받는분주소(전체, 분할)"] = clean_str(vals["받는분주소(전체, 분할)"])
        vals["받는분전화번호"] = clean_phone(vals["받는분전화번호"])
        vals["받는분기타연락처"] = clean_phone(vals["받는분기타연락처"])
        vals["박스수량"] = clean_qty(vals["박스수량"])
        vals["배송메세지1"] = clean_str(vals["배송메세지1"])
        vals["품목명"] = re.sub(r"\s+", " ", clean_str(vals["품목명"]))
        vals["보내는분성명"] = clean_str(vals["보내는분성명"])
        vals["보내는분전화번호"] = clean_phone(vals["보내는분전화번호"])
        vals["보내는분주소(전체, 분할)"] = clean_str(vals["보내는분주소(전체, 분할)"])
        vals["운송장번호"] = clean_str(vals["운송장번호"])
        vals["원본품목(요약용)"] = clean_str(vals["원본품목(요약용)"]) or product_key(vals["품목명"])
        out.append(OrderRow(values=vals, source_file=f"{filename}" + (f" [{sheet}]" if sheet else ""), source_row=rno))
    return out


def parse_order_bytes(data: bytes, filename: str) -> list[OrderRow]:
    """엑셀/CSV 바이트 → OrderRow 목록. 모든 시트를 검사해 발주 헤더가 있는 시트만 읽음."""
    lower = filename.lower()
    orders: list[OrderRow] = []
    if lower.endswith((".xlsx", ".xlsm")):
        wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        for ws in wb.worksheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            got = _rows_to_orders(rows, filename, ws.title if len(wb.worksheets) > 1 else "")
            # 품목요약 같은 집계 시트는 헤더 조건(받는분성함+품목명)을 못 채우므로 자동 제외됨
            orders.extend(got)
    elif lower.endswith(".xls"):
        try:
            import xlrd  # type: ignore
        except ImportError:
            log.error("xls 파일을 읽으려면 xlrd 가 필요합니다: %s", filename)
            return []
        book = xlrd.open_workbook(file_contents=data)
        for sh in book.sheets():
            rows = [sh.row_values(i) for i in range(sh.nrows)]
            orders.extend(_rows_to_orders(rows, filename, sh.name if book.nsheets > 1 else ""))
    elif lower.endswith(".csv"):
        text = None
        for enc in ("utf-8-sig", "cp949", "utf-8"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            return []
        rows = [r for r in csv.reader(io.StringIO(text))]
        orders.extend(_rows_to_orders(rows, filename, ""))
    else:
        log.info("지원하지 않는 첨부 형식 건너뜀: %s", filename)
        return orders
    if not orders:
        log.warning("발주 데이터를 찾지 못함 (받는분성함/품목명 헤더 없음): %s", filename)
    return orders


# ── 집계 ────────────────────────────────────────────────────────────────
@dataclass
class ProductSummary:
    product: str
    count: int          # 건수 (행 수)
    qty: int            # 박스수량 합
    unit_kg: float | None

    @property
    def total_kg(self) -> float | None:
        return round(self.qty * self.unit_kg, 2) if self.unit_kg is not None else None


def summarize_products(rows: Iterable[OrderRow]) -> list[ProductSummary]:
    cnt: Counter = Counter()
    qty: Counter = Counter()
    for r in rows:
        cnt[r.product] += 1
        qty[r.product] += r.qty
    return [ProductSummary(p, cnt[p], qty[p], weight_kg(p)) for p in sorted(cnt, key=product_sort_key)]


def summarize_by_qty(rows: Iterable[OrderRow]) -> list[tuple[str, int, int, int]]:
    """(품목, 건당 박스수량, 건수, 운송장등록건수) - '상품 갯수별 분류'."""
    groups: dict[tuple[str, int], list[OrderRow]] = defaultdict(list)
    for r in rows:
        groups[(r.product, r.qty)].append(r)
    out = []
    for (p, q), rs in sorted(groups.items(), key=lambda kv: (product_sort_key(kv[0][0]), kv[0][1])):
        out.append((p, q, len(rs), sum(1 for r in rs if r.tracking)))
    return out


def dedup_rows(rows: list[OrderRow]) -> tuple[list[OrderRow], int]:
    seen = set()
    out = []
    dup = 0
    for r in rows:
        k = (r.vendor_email, r.dedup_key())
        if k in seen:
            dup += 1
            continue
        seen.add(k)
        out.append(r)
    return out, dup


# ── 회신 매칭 ───────────────────────────────────────────────────────────
def match_reply_rows(original: list[OrderRow], reply: list[OrderRow]) -> tuple[int, list[OrderRow]]:
    """회신 엑셀의 행을 원본 발주 행에 매칭해 운송장번호(및 비어있던 값)를 채움.

    엄격한 키(이름+전화+품목)부터 느슨한 키(이름+주소앞부분, 이름만)까지 차례로 시도합니다.
    같은 키에 후보가 둘 이상(동명이인 등)이면 그 단계에서는 맞추지 않고 다음 단계로 넘깁니다.
    반환: (매칭 건수, 매칭 안 된 회신 행 목록)
    """
    if not reply:
        return 0, []
    unmatched_reply: list[OrderRow] = list(reply)
    matched = 0
    used_original: set[int] = set()
    n_levels = len(original[0].match_keys()) if original else 0
    for level in range(n_levels):
        index: dict[tuple, list[int]] = defaultdict(list)
        for i, o in enumerate(original):
            if i in used_original:
                continue
            k = o.match_keys()[level]
            if all(k):
                index[k].append(i)
        reply_count: Counter = Counter()
        for rr in unmatched_reply:
            k = rr.match_keys()[level]
            if all(k):
                reply_count[k] += 1
        still: list[OrderRow] = []
        for rr in unmatched_reply:
            k = rr.match_keys()[level]
            cands = index.get(k, []) if all(k) else []
            # 후보가 1개이고 회신 쪽도 그 키가 1개일 때(유일 매칭)만 확정. 엄격한 처음 3단계는 순서대로 소진 허용.
            if cands and (level < 3 or (len(cands) == 1 and reply_count[k] == 1)):
                oi = cands.pop(0)
                _apply_reply(original[oi], rr)
                used_original.add(oi)
                matched += 1
            else:
                still.append(rr)
        unmatched_reply = still
        if not unmatched_reply:
            break
    # 마지막 수단: 남은 건수가 같으면 순서대로
    remaining_orig = [i for i in range(len(original)) if i not in used_original]
    if unmatched_reply and len(remaining_orig) == len(unmatched_reply):
        for oi, rr in zip(remaining_orig, unmatched_reply):
            _apply_reply(original[oi], rr)
            matched += 1
        unmatched_reply = []
    return matched, unmatched_reply


def _apply_reply(o: OrderRow, r: OrderRow) -> None:
    for col in ("운송장번호", "받는분주소(전체, 분할)", "받는분전화번호", "받는분우편번호", "박스수량", "배송메세지1"):
        new = clean_str(r.values.get(col))
        old = clean_str(o.values.get(col))
        if not new or new == old or _masked(new):
            continue
        if col == "운송장번호" or not old or col == "박스수량":
            o.changed[col] = (old, new)
            o.values[col] = r.values.get(col)


# ── 쓰기 ────────────────────────────────────────────────────────────────
def _style_header(ws, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = BOLD
        cell.fill = GREY
        cell.border = BORDER
        cell.alignment = CENTER


def _write_order_sheet(ws, rows: list[OrderRow], highlight_missing: bool = True) -> None:
    ws.append(COLUMNS)
    _style_header(ws, len(COLUMNS))
    for r in rows:
        ws.append([r.values.get(c, "") for c in COLUMNS])
        rno = ws.max_row
        for ci, col in enumerate(COLUMNS, start=1):
            cell = ws.cell(row=rno, column=ci)
            cell.border = BORDER
            if highlight_missing and col in ("받는분주소(전체, 분할)", "받는분전화번호") and not clean_str(cell.value):
                cell.fill = YELLOW
            if col in r.changed:
                cell.fill = GREEN
    for col, w in COL_WIDTHS.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{ws.max_row}"


def _write_table(ws, header: list[str], body: list[list[Any]], widths: dict[str, int] | None = None, total_row: bool = False):
    ws.append(header)
    _style_header(ws, len(header))
    for row in body:
        ws.append(row)
        for ci in range(1, len(header) + 1):
            ws.cell(row=ws.max_row, column=ci).border = BORDER
    if total_row and body:
        ws.cell(row=ws.max_row, column=1).font = BOLD
    for col, w in (widths or {}).items():
        ws.column_dimensions[col].width = w


def build_consolidated_xlsx(rows: list[OrderRow], target: date, notes: list[str] | None = None) -> bytes:
    """박경원님께 보낼 통합발주서 (통합발주서 / 품목요약 / 업체별요약 시트)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "통합발주서"
    _write_order_sheet(ws, rows)
    n = max(ws.max_row, 2)

    ws2 = wb.create_sheet("품목요약")
    summary = summarize_products(rows)
    ws2.append(["품목", "건수", "수량", "단위중량(kg)", "환산중량(kg)"])
    _style_header(ws2, 5)
    for i, s in enumerate(summary, start=2):
        ws2.append([
            s.product,
            f"=COUNTIF(통합발주서!$M$2:$M${n},$A{i})",
            f"=SUMIF(통합발주서!$M$2:$M${n},$A{i},통합발주서!$F$2:$F${n})",
            s.unit_kg if s.unit_kg is not None else "",
            f"=C{i}*D{i}" if s.unit_kg is not None else "",
        ])
    last = ws2.max_row
    if summary:
        ws2.append(["합계", f"=SUM(B2:B{last})", f"=SUM(C2:C{last})", "", f"=SUM(E2:E{last})"])
        ws2.cell(row=ws2.max_row, column=1).font = BOLD
    for r in range(2, ws2.max_row + 1):
        for c in range(1, 6):
            ws2.cell(row=r, column=c).border = BORDER
    ws2.column_dimensions["A"].width = 18
    ws2.column_dimensions["B"].width = 10
    ws2.column_dimensions["D"].width = 14
    ws2.column_dimensions["E"].width = 14
    ws2.append([])
    missing = [r for r in rows if r.missing_fields]
    if missing:
        ws2.append([f"※ 수령인 정보 미입력 {len(missing)}건 (통합발주서 시트 노란색 셀 확인 필요)"])
    for note in notes or []:
        ws2.append([f"※ {note}"])
    ws2.append([f"※ {target.year}-{target.month:02d}-{target.day:02d} 통합 발주, 총 {len(rows)}건 / {sum(r.qty for r in rows)}박스"])

    ws3 = wb.create_sheet("업체별요약")
    body = []
    for vendor, vrows in group_by_vendor(rows).items():
        prods = ", ".join(f"{s.product} {s.qty}" for s in summarize_products(vrows))
        body.append([vendor, len(vrows), sum(r.qty for r in vrows), prods])
    _write_table(ws3, ["업체(보내는분)", "건수", "박스수량", "품목별 수량"], body, {"A": 22, "B": 8, "C": 10, "D": 60})
    return _to_bytes(wb)


def build_vendor_xlsx(vendor_label: str, rows: list[OrderRow], target: date) -> bytes:
    """업체별 회신 엑셀 (발주내역 / 상품별수량 / 운송장조회 시트)."""
    rows = sorted(rows, key=lambda r: (product_sort_key(r.product), r.qty, clean_str(r["받는분성함"])))
    wb = Workbook()
    ws = wb.active
    ws.title = "발주내역"
    _write_order_sheet(ws, rows, highlight_missing=False)

    ws2 = wb.create_sheet("상품별수량")
    body = [[p, q, c, c * q, t] for p, q, c, t in summarize_by_qty(rows)]
    if body:
        body.append(["합계", "", sum(b[2] for b in body), sum(b[3] for b in body), sum(b[4] for b in body)])
    _write_table(ws2, ["품목", "건당 박스수량", "건수", "총 박스", "운송장 등록건수"], body,
                 {"A": 20, "B": 14, "C": 8, "D": 10, "E": 16}, total_row=True)
    ws2.append([])
    ws2.append([f"※ {target.month}월 {target.day}일 영암부부농원 발주 · {vendor_label} · 총 {len(rows)}건 / {sum(r.qty for r in rows)}박스"])

    ws3 = wb.create_sheet("운송장조회")
    body3 = [[r["받는분성함"], r["받는분전화번호"], r["품목명"], r.qty, r.tracking or "(미등록)"] for r in rows]
    _write_table(ws3, ["받는분성함", "받는분전화번호", "품목명", "박스수량", "운송장번호"], body3,
                 {"A": 12, "B": 16, "C": 22, "D": 10, "E": 18})
    return _to_bytes(wb)


def group_by_vendor(rows: Iterable[OrderRow]) -> "OrderedDict[str, list[OrderRow]]":
    groups: OrderedDict[str, list[OrderRow]] = OrderedDict()
    for r in rows:
        label = r.vendor_name or clean_str(r["보내는분성명"]) or r.vendor_email or "(미지정)"
        groups.setdefault(label, []).append(r)
    return groups


def _to_bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
