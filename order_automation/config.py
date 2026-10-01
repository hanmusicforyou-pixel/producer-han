"""설정 로더 - .env 또는 환경변수(GitHub Secrets)에서 값을 읽습니다."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

KST = ZoneInfo("Asia/Seoul")


def _bool(v: str | None, default: bool) -> bool:
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


def _time(v: str | None, default: str) -> time:
    s = (v or default).strip()
    h, m = s.split(":")[:2]
    return time(int(h), int(m))


def _date(v: str | None, default: str) -> date:
    return date.fromisoformat((v or default).strip())


@dataclass
class Config:
    naver_id: str
    naver_password: str
    my_name: str
    my_phone: str
    supplier_email: str
    supplier_name: str
    notify_email: str
    subject_keyword: str
    collect_time: time
    reply_check_interval_min: int
    lookback_days: int
    end_date: date
    send_to_vendors: bool
    vendor_mail_cc_me: bool
    data_dir: Path
    templates_dir: Path

    @property
    def my_address(self) -> str:
        return self.naver_id if "@" in self.naver_id else f"{self.naver_id}@naver.com"

    @property
    def notify_address(self) -> str:
        return self.notify_email or self.my_address

    def validate(self) -> list[str]:
        problems = []
        if not self.naver_id or self.naver_id.startswith("your_"):
            problems.append("NAVER_ID 가 설정되지 않았습니다.")
        if not self.naver_password or self.naver_password.startswith(("your_", "여기에")):
            problems.append("NAVER_APP_PASSWORD 가 설정되지 않았습니다.")
        if not self.supplier_email or "@" not in self.supplier_email:
            problems.append("SUPPLIER_EMAIL 이 올바르지 않습니다.")
        return problems


def load_config() -> Config:
    env = os.environ.get
    return Config(
        naver_id=env("NAVER_ID", "k333896").strip(),
        naver_password=env("NAVER_APP_PASSWORD", "").strip(),
        my_name=env("MY_NAME", "담당자").strip(),
        my_phone=env("MY_PHONE", "").strip(),
        supplier_email=env("SUPPLIER_EMAIL", "kwpark462@naver.com").strip(),
        supplier_name=env("SUPPLIER_NAME", "박경원").strip(),
        notify_email=env("NOTIFY_EMAIL", "").strip(),
        subject_keyword=env("SUBJECT_KEYWORD", "영암부부농원 발주서").strip(),
        collect_time=_time(env("COLLECT_TIME"), "10:00"),
        reply_check_interval_min=int(env("REPLY_CHECK_INTERVAL_MIN", "30")),
        lookback_days=int(env("LOOKBACK_DAYS", "3")),
        end_date=_date(env("END_DATE"), "2026-10-30"),
        send_to_vendors=_bool(env("SEND_TO_VENDORS"), True),
        vendor_mail_cc_me=_bool(env("VENDOR_MAIL_CC_ME"), False),
        data_dir=Path(env("DATA_DIR", str(BASE_DIR / "data"))),
        templates_dir=BASE_DIR / "templates",
    )
