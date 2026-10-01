"""네이버 메일 IMAP/SMTP 래퍼.

- IMAP: imap.naver.com:993 (SSL)  - 받은메일함 조회, 첨부 다운로드
- SMTP: smtp.naver.com:465 (SSL)  - 메일 발송
네이버 메일 > 환경설정 > POP3/IMAP 설정에서 IMAP/SMTP 를 '사용함'으로 켜야 합니다.
"""
from __future__ import annotations

import codecs
import email
import imaplib
import logging
import re
import smtplib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from email import policy
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.utils import formataddr, make_msgid, parseaddr, parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Iterable

log = logging.getLogger(__name__)

# 한국 메일 클라이언트가 자주 쓰는 charset 별칭을 파이썬에 등록 (없으면 디코딩 오류)
def _korean_codec(name: str):
    n = name.lower().replace("_", "-")
    if n in ("ks-c-5601-1987", "ks-c-5601-1992", "ks-c-5601", "ksc5601", "ksc-5601", "korean"):
        return codecs.lookup("cp949")
    return None


codecs.register(_korean_codec)

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_UID_RE = re.compile(rb"UID (\d+)")

XLSX_MIME = "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SPREADSHEET_EXT = (".xlsx", ".xlsm", ".xls", ".csv")


def imap_date(d: date) -> str:
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"


def decode_mime(value) -> str:
    if value is None:
        return ""
    try:
        return str(make_header(decode_header(str(value)))).strip()
    except Exception:  # noqa: BLE001
        return str(value).strip()


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


@dataclass
class MailHeader:
    uid: str
    message_id: str
    subject: str
    from_name: str
    from_addr: str
    date: datetime | None
    in_reply_to: str = ""
    references: str = ""

    def short(self) -> str:
        d = self.date.strftime("%m-%d %H:%M") if self.date else "----"
        return f"[{d}] {self.from_addr} | {self.subject}"


@dataclass
class Attachment:
    filename: str
    data: bytes

    @property
    def is_spreadsheet(self) -> bool:
        return self.filename.lower().endswith(SPREADSHEET_EXT)


@dataclass
class SendResult:
    message_id: str
    to: list[str]
    subject: str
    dry_run: bool = False
    saved_to: Path | None = None


class NaverMail:
    IMAP_HOST = "imap.naver.com"
    IMAP_PORT = 993
    SMTP_HOST = "smtp.naver.com"
    SMTP_PORT = 465

    def __init__(self, user_id: str, password: str, display_name: str = "", dry_run: bool = False,
                 outbox_dir: Path | None = None):
        self.login_id = user_id.split("@")[0]
        self.address = user_id if "@" in user_id else f"{user_id}@naver.com"
        self.password = password
        self.display_name = display_name
        self.dry_run = dry_run
        self.outbox_dir = outbox_dir
        self.imap: imaplib.IMAP4_SSL | None = None

    # ── IMAP ────────────────────────────────────────────────────────────
    def connect(self) -> "NaverMail":
        self.imap = imaplib.IMAP4_SSL(self.IMAP_HOST, self.IMAP_PORT)
        try:
            self.imap.login(self.login_id, self.password)
        except imaplib.IMAP4.error:
            self.imap.login(self.address, self.password)
        self.imap.select("INBOX")
        log.info("IMAP 로그인 성공: %s", self.address)
        return self

    def close(self) -> None:
        if self.imap is not None:
            try:
                self.imap.close()
                self.imap.logout()
            except Exception:  # noqa: BLE001
                pass
            self.imap = None

    def __enter__(self) -> "NaverMail":
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()

    def _require_imap(self) -> imaplib.IMAP4_SSL:
        if self.imap is None:
            raise RuntimeError("IMAP 연결이 없습니다. connect() 먼저 호출하세요.")
        return self.imap

    def list_headers(self, since: date) -> list[MailHeader]:
        """since 날짜 이후 받은메일함 전체 헤더(제목/보낸사람/날짜/ID)만 가볍게 조회."""
        imap = self._require_imap()
        typ, data = imap.uid("search", None, "SINCE", imap_date(since))
        if typ != "OK":
            raise RuntimeError(f"IMAP SEARCH 실패: {typ} {data}")
        uids = data[0].split() if data and data[0] else []
        if not uids:
            return []
        headers: list[MailHeader] = []
        fields = "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE MESSAGE-ID IN-REPLY-TO REFERENCES)])"
        for i in range(0, len(uids), 200):
            chunk = b",".join(uids[i:i + 200]).decode()
            typ, items = imap.uid("fetch", chunk, fields)
            if typ != "OK":
                raise RuntimeError(f"IMAP FETCH 실패: {typ}")
            for idx, item in enumerate(items):
                if not isinstance(item, tuple) or len(item) < 2:
                    continue
                m = _UID_RE.search(item[0])
                if not m and idx + 1 < len(items) and isinstance(items[idx + 1], bytes):
                    m = _UID_RE.search(items[idx + 1])  # 일부 서버는 UID 를 본문 뒤에 붙여 보냄
                if not m:
                    continue
                msg = email.message_from_bytes(item[1])
                name, addr = parseaddr(decode_mime(msg.get("From")))
                try:
                    dt = parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
                    if dt is not None and dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                except Exception:  # noqa: BLE001
                    dt = None
                headers.append(MailHeader(
                    uid=m.group(1).decode(),
                    message_id=(msg.get("Message-ID") or "").strip(),
                    subject=decode_mime(msg.get("Subject")),
                    from_name=name.strip(),
                    from_addr=addr.strip().lower(),
                    date=dt,
                    in_reply_to=(msg.get("In-Reply-To") or "").strip(),
                    references=(msg.get("References") or "").strip(),
                ))
        headers.sort(key=lambda h: h.date.timestamp() if h.date else 0)
        return headers

    def fetch(self, uid: str) -> Message:
        imap = self._require_imap()
        typ, data = imap.uid("fetch", uid, "(BODY.PEEK[])")
        if typ != "OK":
            raise RuntimeError(f"IMAP FETCH 실패 uid={uid}")
        raw = b""
        for item in data:
            if isinstance(item, tuple) and len(item) >= 2:
                raw = item[1]
                break
        return email.message_from_bytes(raw, policy=policy.default)

    @staticmethod
    def attachments(msg: Message) -> list[Attachment]:
        out: list[Attachment] = []
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            filename = part.get_filename()
            disp = (part.get("Content-Disposition") or "").lower()
            ctype = part.get_content_type().lower()
            looks_like_file = bool(filename) or "attachment" in disp or "sheet" in ctype or "excel" in ctype
            if not looks_like_file:
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            name = decode_mime(filename) if filename else f"attachment_{len(out) + 1}"
            if "." not in name and ("sheet" in ctype or "excel" in ctype):
                name += ".xlsx"
            out.append(Attachment(filename=name, data=payload))
        return out

    @staticmethod
    def body_text(msg: Message) -> str:
        try:
            body = msg.get_body(preferencelist=("plain", "html"))
        except Exception:  # noqa: BLE001
            body = None
        if body is None:
            return ""
        content = body.get_content()
        if body.get_content_type() == "text/html":
            return _strip_html(content)
        return content.strip()

    # ── SMTP ────────────────────────────────────────────────────────────
    def send(self, to: Iterable[str], subject: str, text: str, html: str | None = None,
             attachments: Iterable[tuple[str, bytes]] = (), cc: Iterable[str] = (),
             bcc: Iterable[str] = (), in_reply_to: str | None = None) -> SendResult:
        to = [t for t in to if t]
        cc = [c for c in cc if c]
        bcc = [b for b in bcc if b]
        msg = EmailMessage()
        msg["From"] = formataddr((self.display_name, self.address)) if self.display_name else self.address
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain="naver.com")
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
        for name, data in attachments:
            lower = name.lower()
            if lower.endswith(".xlsx") or lower.endswith(".xlsm"):
                maintype, subtype = "application", XLSX_MIME
            elif lower.endswith(".xls"):
                maintype, subtype = "application", "vnd.ms-excel"
            elif lower.endswith(".csv"):
                maintype, subtype = "text", "csv"
            else:
                maintype, subtype = "application", "octet-stream"
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)

        result = SendResult(message_id=msg["Message-ID"], to=to + cc + bcc, subject=subject, dry_run=self.dry_run)
        if self.dry_run:
            if self.outbox_dir:
                self.outbox_dir.mkdir(parents=True, exist_ok=True)
                safe = re.sub(r"[^\w가-힣.\-]+", "_", subject)[:60]
                path = self.outbox_dir / f"{datetime.now().strftime('%H%M%S')}_{safe}.eml"
                path.write_bytes(bytes(msg))
                result.saved_to = path
            log.info("[DRY-RUN] 발송 생략 → %s | %s", result.to, subject)
            return result

        with smtplib.SMTP_SSL(self.SMTP_HOST, self.SMTP_PORT, timeout=60) as smtp:
            try:
                smtp.login(self.login_id, self.password)
            except smtplib.SMTPAuthenticationError:
                smtp.login(self.address, self.password)
            smtp.send_message(msg, from_addr=self.address, to_addrs=to + cc + bcc)
        log.info("발송 완료 → %s | %s", result.to, subject)
        return result
