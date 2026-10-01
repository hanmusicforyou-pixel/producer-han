#!/bin/bash
# 자동 실행 해제
LABEL="com.producerhan.yeongam-order"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
rm -f "$PLIST"
echo "✔ 자동 실행 해제 완료"
echo "  (09:55 자동 켜짐을 설정했다면: sudo pmset repeat cancel)"
