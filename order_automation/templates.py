"""메일 본문 렌더링 (templates/*.txt 를 읽어 {변수} 치환, 텍스트 + HTML 두 버전 생성)."""
from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path
from typing import Any, Sequence

WEEKDAYS = "월화수목금토일"


def date_kor(d: date, weekday: bool = True) -> str:
    s = f"{d.year}년 {d.month}월 {d.day}일"
    return f"{s}({WEEKDAYS[d.weekday()]})" if weekday else s


def date_short(d: date) -> str:
    return f"{d.month}월 {d.day}일"


def time_kor(h: int, m: int) -> str:
    return f"{h}시" if m == 0 else f"{h}시 {m:02d}분"


def load_template(templates_dir: Path, name: str) -> str:
    path = templates_dir / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"템플릿이 없습니다: {path}")
    return path.read_text(encoding="utf-8")


def text_table(header: Sequence[str], rows: Sequence[Sequence[Any]], indent: str = "   ") -> str:
    """메일 텍스트용 간단 표. 한글 폭 때문에 완전 정렬은 포기하고 구분자 중심."""
    lines = [indent + " | ".join(str(h) for h in header)]
    lines.append(indent + "-" * max(20, min(60, len(lines[0]) * 2)))
    for r in rows:
        lines.append(indent + " | ".join("" if v is None else str(v) for v in r))
    return "\n".join(lines)


def html_table(header: Sequence[str], rows: Sequence[Sequence[Any]], bold_last: bool = False) -> str:
    th = "".join(f'<th style="border:1px solid #bbb;padding:4px 8px;background:#f1f1f1;text-align:left">{html.escape(str(h))}</th>' for h in header)
    body = []
    for i, r in enumerate(rows):
        weight = "font-weight:bold;" if bold_last and i == len(rows) - 1 else ""
        tds = "".join(f'<td style="border:1px solid #ccc;padding:4px 8px;{weight}">{html.escape("" if v is None else str(v))}</td>' for v in r)
        body.append(f"<tr>{tds}</tr>")
    return f'<table style="border-collapse:collapse;font-size:13px;margin:6px 0 10px 0"><tr>{th}</tr>{"".join(body)}</table>'


_VAR_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _substitute(template: str, ctx: dict[str, Any]) -> str:
    # str.format 대신 정규식 치환: 본문 데이터에 중괄호가 섞여 있어도 깨지지 않음
    return _VAR_RE.sub(lambda m: str(ctx[m.group(1)]) if m.group(1) in ctx else m.group(0), template)


def render(template: str, ctx: dict[str, Any], html_parts: dict[str, str] | None = None) -> tuple[str, str]:
    """(text, html) 반환. html_parts 에 있는 키는 HTML 버전에서 표 HTML 로 바꿔 넣음."""
    text = _substitute(template, ctx)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"

    html_ctx = {k: html.escape(str(v)).replace("\n", "<br>") for k, v in ctx.items()}
    for k in (html_parts or {}):
        html_ctx[k] = f"\x00{k}\x00"  # 자리표시
    body = _substitute(html.escape(template), html_ctx)
    body = re.sub(r"\n{3,}", "\n\n", body).strip().replace("\n", "<br>\n")
    for k, v in (html_parts or {}).items():
        body = body.replace(f"\x00{k}\x00", v)
    html_doc = (
        '<div style="font-family:\'Malgun Gothic\',\'Apple SD Gothic Neo\',sans-serif;font-size:14px;line-height:1.6;color:#222">'
        f"{body}</div>"
    )
    return text, html_doc
