#!/bin/bash
cd "$(dirname "$0")" || exit 1
REPRO="$(cd .. && pwd)"

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
for d in "$HOME"/.workbuddy/binaries/node/versions/*/bin \
         "$HOME"/.nvm/versions/node/*/bin; do
  [ -d "$d" ] && PATH="$d:$PATH"
done
export PATH

G='\033[32m'; R='\033[31m'; Y='\033[33m'; D='\033[2m'; N='\033[0m'
ok()  { printf "  ${G}✓${N} %-16s %s\n" "$1" "${2:-}"; }
bad() { printf "  ${R}✗${N} %-16s %s\n" "$1" "${2:-}"; }
warn(){ printf "  ${Y}!${N} %-16s %s\n" "$1" "${2:-}"; }
sec() { printf "\n${D}%s${N}\n" "$1"; }

try() { "$1" -c "import $2" >/dev/null 2>&1; }

printf "Spine 工作台 · 环境检查\n"
printf "仓库  %s\n" "$REPRO"

sec "Python · 跑拆分/切件/绑骨（要 numpy + PIL）"
WORK_PY=""
for p in \
         "$REPRO/../.workbuddy/binaries/python/envs/spine-p0/bin/python" \
         "$HOME/.workbuddy/binaries/python/envs/spine-p0/bin/python" \
         "$HOME/ComfyUI-Installs/ComfyUI/ComfyUI/.venv/bin/python" \
         "$(command -v python3)"; do
  [ -n "$p" ] && [ -x "$p" ] || continue
  if try "$p" "numpy, PIL"; then WORK_PY="$p"; break; fi
done
if [ -n "$WORK_PY" ]; then
  ok "解释器" "$WORK_PY"
  for m in "PIL" "numpy" "scipy" "psd_tools"; do
    if try "$WORK_PY" "$m"; then ok "$m"; else bad "$m" "缺"; fi
  done
else
  bad "解释器" "找不到同时有 numpy 和 PIL 的 python"
  warn "建议" "见文末「装什么」"
fi

sec "Python · DWPose（要 torch + cv2）"
COMFY="${COMFYUI_DIR:-$HOME/ComfyUI-Installs/ComfyUI/ComfyUI}"
DW_PY=""
for p in "$DWPOSE_PY" "$COMFY/.venv/bin/python" "$COMFY/venv/bin/python" \
         "$(dirname "$COMFY")/standalone-env/bin/python"; do
  [ -n "$p" ] && [ -x "$p" ] || continue
  if try "$p" "torch, cv2"; then DW_PY="$p"; break; fi
done
if [ -n "$DW_PY" ]; then
  ok "解释器" "$DW_PY"
  for m in torch cv2 numpy onnxruntime; do
    if try "$DW_PY" "$m"; then ok "$m"; else warn "$m" "缺（② 会退回 cv2.DNN，更慢）"; fi
  done
  if try "$DW_PY" "onnxruntime"; then
    prov=$("$DW_PY" -c "import onnxruntime as o;print(','.join(o.get_available_providers()))" 2>/dev/null)
    case "$prov" in
      *CoreML*) ok "CoreML" "可用，约 0.04s/帧" ;;
      *CUDA*)   ok "CUDA"   "可用" ;;
      *)        warn "加速"  "只有 CPU（约 0.25s/帧）" ;;
    esac
  fi
else
  bad "解释器" "找不到有 torch+cv2 的 python（ComfyUI 的 .venv）"
  warn "覆盖" "可以先 export DWPOSE_PY=/path/to/python"
fi

sec "其它"
if command -v ffmpeg >/dev/null 2>&1; then ok "ffmpeg" "$(command -v ffmpeg)"; else bad "ffmpeg" "缺（动补 ① 抽帧要用）"; fi
CK="$COMFY/custom_nodes/comfyui_controlnet_aux/ckpts/yzd-v/DWPose"
if [ -f "$CK/yolox_l.onnx" ] && [ -f "$CK/dw-ll_ucoco_384.onnx" ]; then
  ok "DWPose 模型" "$CK"
else
  bad "DWPose 模型" "缺 yolox_l.onnx / dw-ll_ucoco_384.onnx"
fi
if [ -d "$COMFY/custom_nodes/ComfyUI-See-through" ]; then
  ok "See-through" "已装"
else
  warn "See-through" "没装（拆分层要用）"
fi

printf "\n"
if [ -n "$WORK_PY" ] && [ -n "$DW_PY" ]; then
  printf "${G}可以开工${N}：./run.command 启动工作台\n"
else
  printf "${R}还缺东西${N}：见上面标 ✗ 的项\n\n"
  printf "${D}装什么：\n"
  printf "  pip 装到上面「脚本用的解释器」：\n"
  printf "    pip install pillow numpy scipy psd-tools\n"
  printf "  DWPose 的解释器要 torch + opencv + onnxruntime（通常就是 ComfyUI 的 .venv）。\n"
  printf "  没有 ComfyUI 的话：https://github.com/comfyanonymous/ComfyUI\n"
  printf "  node / ffmpeg：brew install node ffmpeg\n"
  printf "  spine-core：cd %s/ws && npm install${N}\n" "$REPRO"
fi
printf "\n按回车关闭…"
read -r _
