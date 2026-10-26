#!/bin/sh

set -e
HERE=$(cd "$(dirname "$0")" && pwd)

for d in /opt/homebrew/bin /usr/local/bin /opt/local/bin \
         "$HOME"/.workbuddy/binaries/node/versions/*/bin \
         "$HOME"/.nvm/versions/node/*/bin; do
  [ -d "$d" ] || continue
  case ":$PATH:" in *":$d:"*) ;; *) PATH="$d:$PATH" ;; esac
done
export PATH

LABEL=local.spine-studio
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PORT=${PORT:-8765}
URL="http://127.0.0.1:$PORT/"
MYUID=$(id -u)
LOG="$HERE/.cache/login.log"
mkdir -p "$HERE/.cache"

find_py() {
  for p in "$HOME/.workbuddy/binaries/python/envs/spine-p0/bin/python" python3; do
    command -v "$p" >/dev/null 2>&1 && { echo "$p"; return 0; }
  done
  return 1
}

port_busy() { /usr/bin/nc -z 127.0.0.1 "$PORT" >/dev/null 2>&1; }
installed() { [ -f "$PLIST" ]; }
running()   { launchctl print "gui/$MYUID/$LABEL" >/dev/null 2>&1; }

usage() {
  cat <<EOF
用法：run.command [--login | --install | --uninstall | --status]
  （不带参数 = 起服务并打开 http://127.0.0.1:$PORT/）
EOF
}

start_login() {
  if port_busy; then
    echo "[$(date '+%F %T')] 端口 $PORT 已在跑，跳过启动" >>"$LOG"
    if [ "${LOGIN_OPEN:-0}" = "1" ]; then open "$URL"; fi
    exit 0
  fi
  PY=$(find_py) || { echo "[$(date '+%F %T')] 找不到 python" >>"$LOG"; exit 1; }
  echo "[$(date '+%F %T')] 启动：$PY $HERE/server.py（PID $$）" >>"$LOG"
  if [ "${LOGIN_OPEN:-0}" = "1" ]; then sleep 1; open "$URL"; fi
  exec "$PY" "$HERE/server.py"
}

start_ui() {
  if port_busy; then
    echo "已在运行 $URL"
    open "$URL" 2>/dev/null || true
    exit 0
  fi
  PY=$(find_py) || { echo "找不到 python（需要 numpy + PIL 的那一个）"; exit 1; }
  "$PY" "$HERE/server.py" &
  SRV=$!
  trap 'kill $SRV 2>/dev/null || true' INT TERM EXIT
  sleep 1
  open "$URL" 2>/dev/null || true
  printf '\n工作台 %s\n素材目录写在页面右上角\n热更新：改 studio/server.py 会自动重启，网页刷新即生效（要关掉用 STUDIO_WATCH=0）\n按 Ctrl-C 停止\n' "$URL"
  wait $SRV
}

install_login() {
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string>
    <string>$HERE/run.command</string>
    <string>--login</string>
  </array>
  <key>WorkingDirectory</key><string>$HERE</string>
  <key>RunAtLoad</key><true/>
  <key>ProcessType</key><string>Interactive</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PORT</key><string>$PORT</string>
    <key>LOGIN_OPEN</key><string>${LOGIN_OPEN:-0}</string>
  </dict>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST_EOF

  if ! /usr/bin/plutil -lint "$PLIST" >/dev/null; then
    rm -f "$PLIST"
    echo "生成的 plist 不合法，已删掉" >&2
    exit 1
  fi
  launchctl bootout "gui/$MYUID/$LABEL" >/dev/null 2>&1 || true
  if launchctl bootstrap "gui/$MYUID" "$PLIST" 2>/dev/null; then
    launchctl enable "gui/$MYUID/$LABEL" >/dev/null 2>&1 || true
    echo "已开启开机自动启动（LaunchAgent）：登录后自动起服务，端口 $PORT"
    echo "  配置 $PLIST"
    echo "  日志 $LOG"
    echo "  现在就已经在跑了：$URL"
    return 0
  fi
  rm -f "$PLIST"
  if add_login_item; then
    echo "已开启开机自动启动（登录项）：登录时由 Terminal 跑一次 run.command --login"
    echo "  想换回更安静的 LaunchAgent 方式：在「终端」里敲一次 $HERE/run.command --install"
    return 0
  fi
  echo "开启失败：launchd 和「登录项」都没成功。" >&2
  echo "  在「终端」窗口里重跑一次：$HERE/run.command --install" >&2
  echo "  （从 Finder/终端里跑才有权限写登录项；本机沙箱里的进程会被挡）" >&2
  return 1
}

add_login_item() {
  remove_login_item
  osascript -e 'tell application "System Events" to make login item at end with properties {name:"Spine 工作台", path:"'"$HERE"'/run.command", hidden:true}' >/dev/null 2>&1
}

remove_login_item() {
  osascript -e 'tell application "System Events" to delete login item "Spine 工作台"' >/dev/null 2>&1 || true
}

has_login_item() {
  osascript -e 'tell application "System Events" to get name of every login item' 2>/dev/null \
    | tr ',' '\n' | grep -q "Spine 工作台"
}

uninstall_login() {
  launchctl bootout "gui/$MYUID/$LABEL" >/dev/null 2>&1 || true
  rm -f "$PLIST"
  remove_login_item
  echo "已关闭开机自动启动（LaunchAgent / 登录项 / 服务都撤了）"
}

status_login() {
  if running; then
    echo "已开启（LaunchAgent）"
    return 0
  fi
  if has_login_item; then
    echo "已开启（登录项）"
    return 0
  fi
  if installed; then
    echo "已配置但没加载"
    return 1
  fi
  echo "未开启"
  return 1
}

case "${1:-}" in
  "")            start_ui ;;
  --login)       start_login ;;
  --install)     install_login ;;
  --uninstall|--remove) uninstall_login ;;
  --status)      status_login ;;
  -h|--help)     usage ;;
  *)             usage; exit 2 ;;
esac
