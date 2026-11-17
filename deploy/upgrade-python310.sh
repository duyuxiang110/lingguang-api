#!/usr/bin/env bash
# Python 3.10 无风险升级脚本（在服务器上执行）：
#   sudo bash /opt/lingguang-api/deploy/upgrade-python310.sh
#
# 步骤：装 python3.10 → 建 venv310 → 装 CPU torch + 业务依赖 → 冒烟验证
#       → 短暂停服切换 venv（旧的备份为 venv_old）→ 健康检查，失败自动回滚。
# 停机窗口：仅 venv 切换 + 服务重启的几秒钟；依赖安装阶段旧服务照常运行。
set -euo pipefail

APP_DIR=/opt/lingguang-api
SERVICE=lingguang-api
NEW_VENV=$APP_DIR/venv310
HEALTH_URL="http://127.0.0.1:8000/api/v2/health"
PIP_MIRROR="https://mirrors.aliyun.com/pypi/simple/"
TORCH_WHEELS="https://mirrors.aliyun.com/pytorch-wheels/cpu/"
TORCH_VER="2.6.0+cpu"   # 阿里云 pytorch-wheels 镜像 cp310 最新版

log() { echo "[upgrade] $*"; }
die() { echo "[upgrade] ❌ $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "请用 sudo 运行: sudo bash $0"
[[ -f $APP_DIR/requirements.txt ]] || die "找不到 $APP_DIR/requirements.txt"
grep -q "simple-lama-inpainting" $APP_DIR/requirements.txt \
  || die "requirements.txt 里没有 simple-lama-inpainting，请先同步最新代码到服务器"

# ===== 0. 磁盘空间（新 venv 约 4GB，旧 venv 保留一份）=====
FREE_GB=$(df -BG --output=avail /opt | tail -1 | tr -dc '0-9')
[[ ${FREE_GB:-0} -ge 6 ]] || die "/opt 可用空间不足 6GB（当前 ${FREE_GB}GB）"
log "磁盘可用 ${FREE_GB}GB，通过"

# ===== 1. 安装 Python 3.10（Ubuntu 22.04+ 原生有；20.04 走 deadsnakes）=====
if ! command -v python3.10 >/dev/null 2>&1; then
  log "安装 python3.10 ..."
  apt-get update -y
  if apt-cache show python3.10 >/dev/null 2>&1; then
    apt-get install -y python3.10 python3.10-venv python3.10-dev
  else
    . /etc/os-release
    [[ "${ID:-}" == "ubuntu" ]] || die "非 Ubuntu 系统，请手动安装 Python 3.10 后重跑"
    apt-get install -y software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -y
    apt-get install -y python3.10 python3.10-venv python3.10-dev
  fi
fi
log "Python: $(python3.10 --version)"

# ===== 2. 新建 venv310（不动现有 venv，服务不中断）=====
log "创建 $NEW_VENV ..."
rm -rf "$NEW_VENV"
python3.10 -m venv "$NEW_VENV"
"$NEW_VENV/bin/pip" install --upgrade pip -i "$PIP_MIRROR" --quiet

# ===== 3. 先装 CPU 版 torch（避免依赖解析拉到 2GB+ 的 CUDA 版）=====
log "安装 torch $TORCH_VER（阿里云镜像）..."
"$NEW_VENV/bin/pip" install "torch==$TORCH_VER" -f "$TORCH_WHEELS" -i "$PIP_MIRROR" --quiet \
  || "$NEW_VENV/bin/pip" install torch --index-url https://download.pytorch.org/whl/cpu --quiet

# ===== 4. 业务依赖 =====
log "安装 requirements.txt ..."
"$NEW_VENV/bin/pip" install -r "$APP_DIR/requirements.txt" -i "$PIP_MIRROR" --quiet
"$NEW_VENV/bin/python" -c "import simple_lama_inpainting, fastapi, paddle; \
print('[upgrade] simple-lama OK, python', __import__('sys').version.split()[0])"

# ===== 5. LaMa 冒烟（模型文件已预置时做真实推理，否则跳过）=====
MODEL_FILE=${LAMA_MODEL:-$APP_DIR/models/big-lama.pt}
if [[ -f $MODEL_FILE ]]; then
  log "真实模型冒烟推理（约 10-30 秒）..."
  cd "$APP_DIR"
  LAMA_MODEL="$MODEL_FILE" "$NEW_VENV/bin/python" - <<'EOF'
from PIL import Image, ImageDraw
from app.services.watermark_service import remove_watermark
img = Image.new("RGB", (197, 115), (70, 130, 180))
m = Image.new("L", (197, 115), 0)
ImageDraw.Draw(m).rectangle([60, 40, 140, 70], fill=255)
img.save("/tmp/_up_img.png"); m.save("/tmp/_up_mask.png")
remove_watermark("/tmp/_up_img.png", "/tmp/_up_mask.png", "/tmp/_up_out.png")
out = Image.open("/tmp/_up_out.png")
assert out.size == (197, 115), f"裁回失败: {out.size}"
print("[upgrade] LaMa 冒烟通过（CPU 加载 + 推理 + 裁回原尺寸）")
EOF
else
  log "⚠️ 未找到模型 $MODEL_FILE，跳过真实推理冒烟（scp 模型后可重跑本脚本）"
fi

# ===== 6. 同步 systemd unit（MemoryMax=2G / LAMA_MODEL 等）=====
if [[ -f $APP_DIR/lingguang-api.service ]]; then
  install -m 644 "$APP_DIR/lingguang-api.service" /etc/systemd/system/$SERVICE.service
  systemctl daemon-reload
  log "systemd unit 已更新"
fi

# ===== 7. 切换 venv + 健康检查（失败自动回滚）=====
rollback() {
  log "回滚到旧 venv ..."
  systemctl stop $SERVICE || true
  [[ -d $APP_DIR/venv ]] && mv "$APP_DIR/venv" "$NEW_VENV"
  [[ -d $APP_DIR/venv_old ]] && mv "$APP_DIR/venv_old" "$APP_DIR/venv"
  systemctl start $SERVICE || true
  die "升级失败，已回滚。排查: journalctl -u $SERVICE -n 50"
}

log "切换 venv（停机数秒）..."
systemctl stop $SERVICE
[[ -d $APP_DIR/venv_old ]] && rm -rf "$APP_DIR/venv_old"
mv "$APP_DIR/venv" "$APP_DIR/venv_old"
mv "$NEW_VENV" "$APP_DIR/venv"
chown -R www-data:www-data "$APP_DIR/venv"
systemctl start $SERVICE

CODE=""
for i in $(seq 1 30); do
  sleep 1
  CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$HEALTH_URL" || true)
  [[ "$CODE" == "200" ]] && break
done
[[ "$CODE" == "200" ]] || rollback

log "✅ 升级完成: $($APP_DIR/venv/bin/python --version)"
log "旧环境保留在 $APP_DIR/venv_old，观察几天无问题后可删: sudo rm -rf $APP_DIR/venv_old"
