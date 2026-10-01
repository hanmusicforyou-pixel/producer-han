"""오프라인 테스트/데모용 가짜 메일함. 실제 네이버에 접속하지 않고 NaverMail 과 같은 인터페이스를 제공합니다."""
from __future__ import annotations

import email
import logging
from datetime import datetime
from email import policy
from email.message import EmailMessage, Message
from email.utils import make_msgid
from pathlib import Path

from naver_mail import Attachment, MailHeader, NaverMail, SendResult, decode_mime

log = logging.getLogger(__name__)


class FakeMail(NaverMail):
    def __init__(self, my_address: str, outbox_dir: Path | None = None):
        super().__init__(my_address, "x", dry_run=True, outbox_dir=outbox_dir)
        self.inbox: list[tuple[MailHeader, Message]] = []
        self.sent: list[tuple[list[str], str, str, list[tuple[str, bytes]]]] = []
        self._uid = 0

    def connect(self):
        return self

    def close(self):
        pass

    def inject(self, from_name: str, from_addr: str, subject: str, text: str, when: datetime,
               attachments: list[tuple[str, bytes]] = (), in_reply_to: str = "") -> MailHeader:
        msg = EmailMessage()
        msg["From"] = f"{from_name} <{from_addr}>"
        msg["To"] = self.address
        msg["Subject"] = subject
        msg["Date"] = email.utils.format_datetime(when)
        msg["Message-ID"] = make_msgid(domain="fake.test")
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        msg.set_content(text)
        for name, data in attachments:
            msg.add_attachment(data, maintype="application",
                               subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=name)
        parsed = email.message_from_bytes(bytes(msg), policy=policy.default)
        self._uid += 1
        h = MailHeader(uid=str(self._uid), message_id=msg["Message-ID"], subject=subject, from_name=from_name,
                       from_addr=from_addr.lower(), date=when, in_reply_to=in_reply_to)
        self.inbox.append((h, parsed))
        return h

    def list_headers(self, since):
        # 데모용: 날짜 필터 없이 전부 반환 (실제 IMAP 은 SINCE 로 서버가 걸러줌)
        return [h for h, _ in self.inbox]

    def fetch(self, uid: str) -> Message:
        for h, m in self.inbox:
            if h.uid == uid:
                return m
        raise KeyError(uid)

    def send(self, to, subject, text, html=None, attachments=(), cc=(), bcc=(), in_reply_to=None) -> SendResult:
        attachments = list(attachments)
        res = super().send(to, subject, text, html, attachments, cc, bcc, in_reply_to)
        self.sent.append((list(to), subject, text, attachments))
        # 내 주소로 보낸 메일은 받은메일함에도 들어온 것으로 처리 (완료 표시 메일 감지용)
        if any(t.lower() == self.address.lower() for t in to):
            from config import KST
            self.inject(self.display_name or "me", self.address, subject, text, datetime.now(KST), attachments)
        return res
