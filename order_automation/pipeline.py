"""발주 자동화 파이프라인.

1단계 collect     : 업체 발주서 메일 수집 → 통합발주서 생성 → 박경원님께 발송 → 나에게 요약
2단계 check_reply : 박경원님 회신 감지 → 운송장번호 매칭 → 업체별 엑셀+안내문 발송 → 나에게 요약

상태 저장소는 '내 받은메일함' 자체입니다. 단계별 완료 메일을 나에게 보내고(제목 앞 [자동발주 n단계]),
다음 실행 때 그 메일이 있으면 같은 단계를 두 번 하지 않습니다. 그래서 PC·GitHub Actions 어디서 돌려도 중복 발송이 없습니다.
"""
from __future__ import annotations

import json
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import order_excel as oe
import templates as T
from config import KST, Config
from naver_mail import Attachment, MailHeader, NaverMail

log = logging.getLogger(__name__)

MARK_A = "[자동발주 1단계]"
MARK_B = "[자동발주 2단계]"
MARK_NONE = "[자동발주 미접수]"
MARK_LATE = "[자동발주 지각접수]"
MARK_FAIL = "[자동발주 오류]"
SYSTEM_FOOTER = "----- system -----"


def build_subject_regex(keyword: str) -> re.Pattern:
    # "영암부부농원 발주서" → 영\s*암\s*부\s*부\s*농\s*원\s*발\s*주\s*서  (띄어쓰기 차이 허용)
    chars = [re.escape(ch) for ch in keyword if not ch.isspace()]
    return re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*" + r"\s*".join(chars))


@dataclass
class VendorInfo:
    email: str
    name: str
    message_ids: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    rows: list[oe.OrderRow] = field(default_factory=list)

    @property
    def qty(self) -> int:
        return sum(r.qty for r in self.rows)


class Pipeline:
    def __init__(self, cfg: Config, mail: NaverMail, dry_run: bool = False):
        self.cfg = cfg
        self.mail = mail
        self.dry_run = dry_run
        self.subject_re = build_subject_regex(cfg.subject_keyword)
        self._headers: list[MailHeader] | None = None

    # ── 공용 ────────────────────────────────────────────────────────────
    def now(self) -> datetime:
        return datetime.now(KST)

    def today(self) -> date:
        return self.now().date()

    def day_dir(self, target: date) -> Path:
        d = self.cfg.data_dir / target.isoformat()
        d.mkdir(parents=True, exist_ok=True)
        return d

    def is_me(self, addr: str) -> bool:
        return addr.lower() in {self.cfg.my_address.lower(), self.cfg.notify_address.lower()}

    def owner_recipients(self) -> list[str]:
        """요약/완료 메일 수신자. 완료 표시는 네이버 받은메일함에 있어야 하므로 내 네이버 주소는 항상 포함."""
        out = [self.cfg.my_address]
        if self.cfg.notify_address.lower() != self.cfg.my_address.lower():
            out.append(self.cfg.notify_address)
        return out

    def is_supplier(self, addr: str) -> bool:
        return addr.lower() == self.cfg.supplier_email.lower()

    def headers(self, target: date, refresh: bool = False) -> list[MailHeader]:
        if self._headers is None or refresh:
            since = target - timedelta(days=self.cfg.lookback_days)
            self._headers = self.mail.list_headers(since)
            log.info("받은메일함 %s 이후 메일 %d건 조회", since, len(self._headers))
        return self._headers

    def subject_date(self, subject: str) -> tuple[int, int] | None:
        m = self.subject_re.search(subject or "")
        return (int(m.group(1)), int(m.group(2))) if m else None

    def find_marker(self, target: date, mark: str, extra: str = "") -> MailHeader | None:
        prefix = f"{mark} {T.date_short(target)}" + (f" {extra}" if extra else "")
        found = [h for h in self.headers(target) if self.is_me(h.from_addr) and h.subject.startswith(prefix)]
        return found[-1] if found else None

    def vendor_headers(self, target: date) -> list[MailHeader]:
        out = []
        for h in self.headers(target):
            if self.is_me(h.from_addr) or self.is_supplier(h.from_addr):
                continue
            md = self.subject_date(h.subject)
            if md == (target.month, target.day):
                out.append(h)
        return out

    def load_vendors(self, hdrs: list[MailHeader]) -> "OrderedDict[str, VendorInfo]":
        vendors: OrderedDict[str, VendorInfo] = OrderedDict()
        for h in hdrs:
            v = vendors.setdefault(h.from_addr, VendorInfo(email=h.from_addr, name=h.from_name or h.from_addr.split("@")[0]))
            v.message_ids.append(h.message_id)
            msg = self.mail.fetch(h.uid)
            sheets = [a for a in self.mail.attachments(msg) if a.is_spreadsheet]
            if not sheets:
                v.problems.append(f"'{h.subject}' 메일에 엑셀 첨부가 없음")
                continue
            for a in sheets:
                rows = oe.parse_order_bytes(a.data, a.filename)
                v.files.append(f"{a.filename} ({len(rows)}건)")
                if not rows:
                    v.problems.append(f"{a.filename}: 발주 데이터를 읽지 못함 (헤더 확인 필요)")
                for r in rows:
                    r.vendor_email = v.email
                    r.vendor_name = v.name
                v.rows.extend(rows)
        for v in vendors.values():
            if v.rows and (not v.name or v.name == v.email.split("@")[0]):
                sender = oe.clean_str(v.rows[0]["보내는분성명"])
                if sender:
                    v.name = sender
                    for r in v.rows:
                        r.vendor_name = sender
            v.rows, dup = oe.dedup_rows(v.rows)
            if dup:
                v.problems.append(f"중복 행 {dup}건 제거")
        return vendors

    def all_rows(self, vendors: "OrderedDict[str, VendorInfo]") -> list[oe.OrderRow]:
        return [r for v in vendors.values() for r in v.rows]

    def base_ctx(self, target: date) -> dict[str, Any]:
        ct = self.cfg.collect_time
        return {
            "my_name": self.cfg.my_name,
            "my_phone": self.cfg.my_phone,
            "my_email": self.cfg.my_address,
            "supplier_name": self.cfg.supplier_name,
            "date_kor": T.date_kor(target),
            "date_short": T.date_short(target),
            "deadline_kor": T.time_kor(ct.hour, ct.minute),
            "end_date_kor": T.date_kor(self.cfg.end_date, weekday=False),
        }

    @staticmethod
    def product_tables(summary: list[oe.ProductSummary]) -> tuple[str, str]:
        header = ["품목", "건수", "수량(박스)", "환산중량(kg)"]
        body = [[s.product, s.count, s.qty, s.total_kg if s.total_kg is not None else "-"] for s in summary]
        kg = sum(s.total_kg for s in summary if s.total_kg is not None)
        body.append(["합계", sum(s.count for s in summary), sum(s.qty for s in summary), round(kg, 2)])
        return T.text_table(header, body), T.html_table(header, body, bold_last=True)

    def save_state(self, target: date, data: dict) -> None:
        path = self.day_dir(target) / "state.json"
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        old.update(data)
        path.write_text(json.dumps(old, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # ── 1단계 ───────────────────────────────────────────────────────────
    def collect(self, target: date, force: bool = False) -> dict:
        if target > self.cfg.end_date:
            log.info("운영 종료일(%s) 이후 → 수집 안 함", self.cfg.end_date)
            return {"status": "expired"}
        if not force and self.find_marker(target, MARK_A):
            log.info("%s 1단계 이미 완료 (완료 메일 존재)", target)
            return {"status": "already_done"}

        hdrs = self.vendor_headers(target)
        log.info("%s 업체 발주서 메일 %d건: %s", T.date_short(target), len(hdrs), [h.short() for h in hdrs])
        if not hdrs:
            if not self.find_marker(target, MARK_NONE):
                self.mail.send(
                    self.owner_recipients(),
                    f"{MARK_NONE} {T.date_short(target)} 영암부부농원 발주서 메일이 아직 없습니다",
                    f"{T.date_kor(target)} {T.time_kor(self.cfg.collect_time.hour, self.cfg.collect_time.minute)} 기준으로 "
                    f"제목이 '{T.date_short(target)} {self.cfg.subject_keyword}' 인 메일이 받은메일함에 없습니다.\n"
                    f"이후 {self.cfg.reply_check_interval_min}분마다 다시 확인하며, 도착하면 자동으로 통합발주를 진행합니다.\n"
                    f"(이 안내는 하루 한 번만 발송됩니다)",
                )
            return {"status": "no_vendor_mail"}

        vendors = self.load_vendors(hdrs)
        rows = self.all_rows(vendors)
        problems = [f"{v.name}: {p}" for v in vendors.values() for p in v.problems]
        if not rows:
            if not self.find_marker(target, MARK_FAIL):
                self.mail.send(
                    self.owner_recipients(),
                    f"{MARK_FAIL} {T.date_short(target)} 발주서 첨부를 읽지 못했습니다",
                    "메일은 왔지만 엑셀에서 발주 데이터를 읽지 못했습니다. 첨부 양식(받는분성함/품목명 헤더)을 확인해 주세요.\n\n"
                    + "\n".join(problems),
                )
            return {"status": "parse_failed", "problems": problems}

        summary = oe.summarize_products(rows)
        box_total = sum(r.qty for r in rows)
        missing = [r for r in rows if r.missing_fields]
        notes = [f"{v.name}: {len(v.rows)}건 / {v.qty}박스 ({', '.join(v.files)})" for v in vendors.values()]
        xlsx = oe.build_consolidated_xlsx(rows, target, notes)
        fname = f"영암부부농원_통합발주서_{target.strftime('%Y%m%d')}.xlsx"
        (self.day_dir(target) / fname).write_bytes(xlsx)

        # 박경원님께 발송
        text_tbl, html_tbl = self.product_tables(summary)
        ctx = self.base_ctx(target) | {
            "vendor_count": len(vendors), "row_count": len(rows), "box_total": box_total,
            "product_table": text_tbl, "attachment_name": fname,
            "missing_note": (f"\n※ 수령인 주소/연락처 미입력 {len(missing)}건이 있습니다 (엑셀 노란색 셀). "
                             f"업체 확인 후 보완 전달하겠습니다.\n" if missing else ""),
        }
        text, html = T.render(T.load_template(self.cfg.templates_dir, "supplier_mail"), ctx, {"product_table": html_tbl})
        supplier_subject = f"{T.date_short(target)} {self.cfg.subject_keyword} (통합 {len(rows)}건)"
        sent = self.mail.send([self.cfg.supplier_email], supplier_subject, text, html, [(fname, xlsx)])

        # 나에게 요약 (= 1단계 완료 표시)
        vheader = ["업체", "메일", "건수", "박스", "첨부파일", "비고"]
        vbody = [[v.name, v.email, len(v.rows), v.qty, "; ".join(v.files), "; ".join(v.problems)] for v in vendors.values()]
        miss_lines = [f"- {r.vendor_name} / {r['받는분성함']} / {r['품목명']} : {', '.join(r.missing_fields)} 없음" for r in missing]
        footer = "\n".join([
            SYSTEM_FOOTER,
            f"target={target.isoformat()}",
            f"supplier_msgid={sent.message_id}",
            "vendor_msgids=" + ",".join(mid for v in vendors.values() for mid in v.message_ids),
        ])
        owner_text = "\n".join(x for x in [
            f"{T.date_kor(target)} 영암부부농원 통합발주를 {self.cfg.supplier_name} 님({self.cfg.supplier_email})께 발송했습니다.",
            f"업체 {len(vendors)}곳 / 총 {len(rows)}건 / {box_total}박스" + (" [DRY-RUN: 실제 발송 안 됨]" if sent.dry_run else ""),
            "", "■ 품목별 합계", text_tbl,
            "", "■ 업체별", T.text_table(vheader, vbody),
            ("\n■ 수령인 정보 미입력 " + f"{len(missing)}건\n" + "\n".join(miss_lines)) if missing else None,
            ("\n■ 확인 필요\n" + "\n".join(f"- {p}" for p in problems)) if problems else None,
            "", f"회신이 오면 {self.cfg.reply_check_interval_min}분 이내에 업체별로 나눠 발송하고 다시 알려드립니다.",
            "", footer,
        ] if x is not None)
        owner_html = T.render(owner_text.replace(text_tbl, "{p}").replace(T.text_table(vheader, vbody), "{v}"),
                              {"p": "", "v": ""}, {"p": html_tbl, "v": T.html_table(vheader, vbody)})[1]
        self.mail.send(
            self.owner_recipients(),
            f"{MARK_A} {T.date_short(target)} 영암부부농원 통합발주 완료 · 업체 {len(vendors)}곳 / {len(rows)}건 / {box_total}박스",
            owner_text, owner_html, [(fname, xlsx)],
        )
        self.save_state(target, {
            "target": target.isoformat(), "phase_a_at": self.now().isoformat(),
            "supplier_msgid": sent.message_id, "supplier_subject": supplier_subject,
            "vendors": {v.email: {"name": v.name, "rows": len(v.rows), "qty": v.qty, "files": v.files,
                                  "message_ids": v.message_ids, "problems": v.problems} for v in vendors.values()},
            "products": [{"product": s.product, "count": s.count, "qty": s.qty, "kg": s.total_kg} for s in summary],
            "consolidated_file": fname,
        })
        self._headers = None  # 방금 보낸 완료 메일이 보이도록 캐시 비움
        return {"status": "sent", "vendors": len(vendors), "rows": len(rows), "boxes": box_total,
                "summary": summary, "problems": problems, "missing": len(missing), "file": fname}

    # ── 2단계 ───────────────────────────────────────────────────────────
    def _read_marker_footer(self, marker: MailHeader) -> dict[str, str]:
        body = self.mail.body_text(self.mail.fetch(marker.uid))
        out: dict[str, str] = {}
        if SYSTEM_FOOTER in body:
            for line in body.split(SYSTEM_FOOTER, 1)[1].splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip()
        return out

    def find_supplier_reply(self, target: date, after: datetime | None, supplier_msgid: str) -> tuple[MailHeader, list[Attachment], str] | None:
        cands = []
        for h in self.headers(target):
            if not self.is_supplier(h.from_addr):
                continue
            if after and h.date and h.date < after - timedelta(minutes=10):
                continue
            cands.append(h)
        if not cands:
            return None
        # 우선순위: 우리가 보낸 메일에 대한 답장 > 제목에 키워드 > 엑셀 첨부가 있는 메일
        def score(h: MailHeader) -> int:
            s = 0
            if supplier_msgid and (supplier_msgid in h.in_reply_to or supplier_msgid in h.references):
                s += 4
            if self.subject_date(h.subject) == (target.month, target.day):
                s += 2
            if self.cfg.subject_keyword.split()[0] in h.subject.replace(" ", ""):
                s += 1
            return s
        cands.sort(key=lambda h: (score(h), h.date.timestamp() if h.date else 0), reverse=True)
        for h in cands:
            msg = self.mail.fetch(h.uid)
            sheets = [a for a in self.mail.attachments(msg) if a.is_spreadsheet]
            if sheets or score(h) > 0:
                return h, sheets, self.mail.body_text(msg)
        return None

    def check_reply(self, target: date) -> dict:
        if self.find_marker(target, MARK_B):
            log.info("%s 2단계 이미 완료", target)
            return {"status": "already_done"}
        mark_a = self.find_marker(target, MARK_A)
        if not mark_a:
            log.info("%s 1단계 미완료 → 회신 확인 생략", target)
            return {"status": "phase_a_pending"}
        meta = self._read_marker_footer(mark_a)
        found = self.find_supplier_reply(target, mark_a.date, meta.get("supplier_msgid", ""))
        if not found:
            log.info("%s 님 회신 아직 없음", self.cfg.supplier_name)
            return {"status": "no_reply"}
        reply_hdr, sheets, reply_body = found
        log.info("회신 감지: %s (첨부 %d개)", reply_hdr.short(), len(sheets))

        # 1단계에서 처리한 업체 메일만 다시 읽어 원본 발주 행 복원 (메일 ID 기준)
        wanted = set(filter(None, meta.get("vendor_msgids", "").split(",")))
        hdrs = [h for h in self.vendor_headers(target) if (h.message_id in wanted)] if wanted else self.vendor_headers(target)
        vendors = self.load_vendors(hdrs)
        rows = self.all_rows(vendors)
        if not rows:
            return {"status": "no_original_rows"}

        reply_rows: list[oe.OrderRow] = []
        for a in sheets:
            reply_rows.extend(oe.parse_order_bytes(a.data, a.filename))
        matched, unmatched = oe.match_reply_rows(rows, reply_rows)
        text_only = not reply_rows
        tracking_total = sum(1 for r in rows if r.tracking)
        log.info("회신 행 %d / 매칭 %d / 미매칭 %d / 운송장 %d", len(reply_rows), matched, len(unmatched), tracking_total)

        ddir = self.day_dir(target)
        for a in sheets:
            (ddir / f"회신_{a.filename}").write_bytes(a.data)

        # 업체별 엑셀 + 안내문
        results = []
        vendor_files: list[tuple[str, bytes]] = []
        tpl = T.load_template(self.cfg.templates_dir, "vendor_notice")
        for v in vendors.values():
            if not v.rows:
                continue
            safe_name = re.sub(r"[\\/:*?\"<>|]+", "_", v.name)
            fname = f"영암부부농원_{target.strftime('%m%d')}_발주결과_{safe_name}.xlsx"
            xlsx = oe.build_vendor_xlsx(v.name, v.rows, target)
            (ddir / fname).write_bytes(xlsx)
            vendor_files.append((fname, xlsx))
            filled = sum(1 for r in v.rows if r.tracking)
            changed = sum(1 for r in v.rows if any(k != "운송장번호" for k in r.changed))
            qty_rows = [[p, q, c, c * q, t] for p, q, c, t in oe.summarize_by_qty(v.rows)]
            header = ["품목", "건당 박스", "건수", "총 박스", "운송장 등록"]
            if filled == len(v.rows):
                tnote = "전체 운송장번호가 등록되었습니다. 첨부 [운송장조회] 시트를 확인해 주세요."
            elif filled == 0:
                tnote = ("영암부부농원에서 발주 확인은 되었으나 운송장번호는 아직 등록 전입니다. 등록되는 대로 다시 안내드립니다."
                         if text_only else "운송장번호가 아직 등록되지 않았습니다. 등록되는 대로 다시 안내드립니다.")
            else:
                tnote = f"미등록 {len(v.rows) - filled}건은 운송장 등록 후 추가 안내드립니다."
            ctx = self.base_ctx(target) | {
                "vendor_name": v.name, "row_count": len(v.rows), "box_total": v.qty,
                "product_table": T.text_table(header, qty_rows), "tracking_filled": filled, "tracking_note": tnote,
                "attachment_name": fname,
                "change_note": (f"\n■ 변경/보완 {changed}건 : 영암부부농원에서 수정한 값은 [발주내역] 시트 연두색 셀로 표시했습니다.\n"
                                if changed else ""),
            }
            text, html = T.render(tpl, ctx, {"product_table": T.html_table(header, qty_rows)})
            subject = f"[영암부부농원] {T.date_short(target)} 발주 처리 결과 안내 - {v.name} ({len(v.rows)}건 / 운송장 {filled}건)"
            status = "미발송(설정)"
            if self.cfg.send_to_vendors:
                cc = [self.cfg.notify_address] if self.cfg.vendor_mail_cc_me else []
                try:
                    res = self.mail.send([v.email], subject, text, html, [(fname, xlsx)], cc=cc)
                    status = "DRY-RUN" if res.dry_run else "발송완료"
                except Exception as e:  # noqa: BLE001
                    log.exception("업체 발송 실패: %s", v.email)
                    status = f"실패: {e}"
            (ddir / f"안내문_{safe_name}.txt").write_text(text, encoding="utf-8")
            results.append([v.name, v.email, len(v.rows), v.qty, f"{filled}/{len(v.rows)}", status])

        # 나에게 요약 (= 2단계 완료 표시)
        rheader = ["업체", "메일", "건수", "박스", "운송장", "발송"]
        un_lines = [f"- {r['받는분성함']} / {r['받는분전화번호']} / {r['품목명']} / 운송장 {r.tracking or '-'}" for r in unmatched]
        snippet = re.sub(r"\n{2,}", "\n", reply_body.strip())[:800]
        owner_text = "\n".join(x for x in [
            f"{T.date_kor(target)} {self.cfg.supplier_name} 님 회신을 확인하고 업체별 발주 결과를 발송했습니다.",
            f"회신 메일: {reply_hdr.subject} ({reply_hdr.date.astimezone(KST).strftime('%m-%d %H:%M') if reply_hdr.date else ''})",
            f"회신 엑셀 {len(reply_rows)}행 / 원본 {len(rows)}건 중 매칭 {matched}건 / 운송장 등록 {tracking_total}건"
            + (" / ※ 엑셀 첨부 없는 텍스트 회신 → 원본 발주 기준으로 분배" if text_only else ""),
            "", "■ 업체별 발송 결과", T.text_table(rheader, results),
            (f"\n■ 원본과 매칭되지 않은 회신 행 {len(unmatched)}건 (수동 확인)\n" + "\n".join(un_lines)) if unmatched else None,
            "", "■ 회신 본문", snippet or "(본문 없음)",
            "", SYSTEM_FOOTER, f"target={target.isoformat()}", f"reply_msgid={reply_hdr.message_id}",
        ] if x is not None)
        owner_html = T.render(owner_text.replace(T.text_table(rheader, results), "{r}"), {"r": ""}, {"r": T.html_table(rheader, results)})[1]
        attachments = vendor_files + [(f"회신_{a.filename}", a.data) for a in sheets]
        self.mail.send(
            self.owner_recipients(),
            f"{MARK_B} {T.date_short(target)} 영암부부농원 업체 안내 발송 완료 · {len(results)}곳 / 운송장 {tracking_total}/{len(rows)}",
            owner_text, owner_html, attachments,
        )
        self.save_state(target, {"phase_b_at": self.now().isoformat(), "reply_msgid": reply_hdr.message_id,
                                 "reply_subject": reply_hdr.subject, "matched": matched, "unmatched": len(unmatched),
                                 "tracking": tracking_total, "vendor_results": results})
        self._headers = None
        return {"status": "sent", "vendors": len(results), "matched": matched, "unmatched": len(unmatched),
                "tracking": tracking_total, "results": results}

    # ── 지각 접수 알림 ──────────────────────────────────────────────────
    def notify_late(self, target: date) -> int:
        mark_a = self.find_marker(target, MARK_A)
        if not mark_a:
            return 0
        processed = set(filter(None, self._read_marker_footer(mark_a).get("vendor_msgids", "").split(",")))
        late = [h for h in self.vendor_headers(target) if h.message_id not in processed]
        count = 0
        for h in late:
            if self.find_marker(target, MARK_LATE, h.from_addr):
                continue
            msg = self.mail.fetch(h.uid)
            sheets = [(a.filename, a.data) for a in self.mail.attachments(msg) if a.is_spreadsheet]
            self.mail.send(
                self.owner_recipients(),
                f"{MARK_LATE} {T.date_short(target)} {h.from_addr} 마감 후 접수 - 수동 처리 필요",
                f"통합발주 발송({mark_a.date.astimezone(KST).strftime('%H:%M') if mark_a.date else ''}) 이후에 발주서가 도착했습니다.\n"
                f"보낸사람: {h.from_name} <{h.from_addr}>\n제목: {h.subject}\n"
                f"받은시각: {h.date.astimezone(KST).strftime('%m-%d %H:%M') if h.date else '-'}\n\n"
                f"이 건은 자동 통합에 포함되지 않았습니다. 첨부를 확인해 {self.cfg.supplier_name} 님께 별도 전달해 주세요.\n"
                f"(업체에는 '오전 {T.time_kor(self.cfg.collect_time.hour, self.cfg.collect_time.minute)} 이후 접수분은 다음 날 반영' 안내가 나가 있습니다)",
                attachments=sheets,
            )
            count += 1
        if count:
            self._headers = None
        return count

    # ── 통합 실행 (스케줄러/GitHub Actions 가 호출) ─────────────────────
    def run(self, target: date | None = None, force: bool = False) -> dict:
        today = self.today()
        target = target or today
        if today > self.cfg.end_date:
            log.info("운영 종료일 %s 이 지났습니다. 아무 작업도 하지 않습니다.", self.cfg.end_date)
            return {"status": "expired"}
        now = self.now()
        out: dict[str, Any] = {"target": target.isoformat(), "now": now.isoformat()}
        self.headers(target, refresh=True)
        if not self.find_marker(target, MARK_A):
            if force or target < today or now.time() >= self.cfg.collect_time:
                out["collect"] = self.collect(target, force=force)
            else:
                out["collect"] = {"status": "before_collect_time"}
                log.info("아직 %s 전 → 수집 대기", self.cfg.collect_time)
        else:
            out["late"] = self.notify_late(target)
        self.headers(target, refresh=True)
        out["reply"] = self.check_reply(target)
        return out

    # ── 업체 공지 (최초 1회) ────────────────────────────────────────────
    def announce(self, recipients: list[str]) -> list:
        ctx = self.base_ctx(self.today())
        nxt = self.today() + timedelta(days=1)
        ctx["example_subject"] = f"{T.date_short(nxt)} {self.cfg.subject_keyword}"
        text, html = T.render(T.load_template(self.cfg.templates_dir, "vendor_announcement"), ctx)
        subject = f"[영암부부농원 발주 접수 안내] 매일 오전 {ctx['deadline_kor']} 마감 · {ctx['end_date_kor']}까지"
        results = []
        for to in recipients:
            results.append(self.mail.send([to], subject, text, html))
        return results

    def render_announcement(self) -> str:
        ctx = self.base_ctx(self.today())
        nxt = self.today() + timedelta(days=1)
        ctx["example_subject"] = f"{T.date_short(nxt)} {self.cfg.subject_keyword}"
        return T.render(T.load_template(self.cfg.templates_dir, "vendor_announcement"), ctx)[0]
