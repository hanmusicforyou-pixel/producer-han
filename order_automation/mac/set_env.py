"""`.env` 의 KEY=값 한 줄을 안전하게 바꿉니다. 값은 환경변수 ENV_VALUE 로 받아 터미널 기록·프로세스 목록에 남지 않게 합니다.

값은 항상 작은따옴표로 감싸 저장합니다(python-dotenv 가 # · 공백 · $ 를 특수문자로 해석하지 않음).
사용: ENV_VALUE='값' python mac/set_env.py KEY [.env 경로]
"""
import os
import re
import sys
from pathlib import Path


def quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def main() -> int:
    if len(sys.argv) < 2 or "ENV_VALUE" not in os.environ:
        print("사용법: ENV_VALUE=값 python set_env.py KEY [경로]", file=sys.stderr)
        return 2
    key = sys.argv[1]
    path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / ".env"
    line = f"{key}={quote(os.environ['ENV_VALUE'])}"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pat = re.compile(rf"^\s*{re.escape(key)}\s*=")
    for i, old in enumerate(lines):
        if pat.match(old):
            lines[i] = line
            break
    else:
        lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)  # 본인만 읽기/쓰기
    return 0


if __name__ == "__main__":
    sys.exit(main())
