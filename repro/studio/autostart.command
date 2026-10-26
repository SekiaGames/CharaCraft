#!/bin/sh

HERE=$(cd "$(dirname "$0")" && pwd)
RUN="$HERE/run.command"
TITLE="Spine 工作台"

STATE=$("$RUN" --status 2>/dev/null)
case "$STATE" in
  已开启*) DEFAULT="关闭开机启动" ;;
  *)       DEFAULT="开启开机启动" ;;
esac

CHOICE=$(osascript <<APPLESCRIPT 2>/dev/null
display dialog "开机自动启动：$STATE

登录后自动起工作台（端口 8765），素材目录用「上次用的那个」。
$HERE" with title "$TITLE" buttons {"取消", "关闭开机启动", "开启开机启动"} default button "$DEFAULT" with icon note
APPLESCRIPT
) || { echo "打不开对话框（没有图形会话？）—— 请改用：$RUN --install / --uninstall"; exit 1; }

CHOICE=${CHOICE#button returned:}

case "$CHOICE" in
  "开启开机启动") OUT=$("$RUN" --install 2>&1); RC=$? ;;
  "关闭开机启动") OUT=$("$RUN" --uninstall 2>&1); RC=$? ;;
  *) exit 0 ;;
esac

MSG=$(printf '%s' "$OUT" | tr '\n' ' ' | sed 's/  */ /g; s/\\/\\\\/g; s/"/\\"/g')
ICON=note
[ "$RC" -eq 0 ] || ICON=stop
osascript -e "display dialog \"$MSG\" with title \"$TITLE\" buttons {\"好\"} default button \"好\" with icon $ICON" >/dev/null 2>&1

exit "$RC"
