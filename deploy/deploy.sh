#!/bin/bash
# 一键发布脚本：本地打包 → scp 上传 → 安装依赖 → 重启服务 → 健康检查
# 用法: ./deploy/deploy.sh
# 需先设置环境变量: export DEPLOY_SERVER=root@<服务器IP>（可写入 ~/.zshrc）
set -e

# ===== 配置 =====
# 服务器地址从环境变量读取，避免提交到公开仓库后暴露服务器 IP
SERVER="${DEPLOY_SERVER:?请先设置环境变量 DEPLOY_SERVER，如: export DEPLOY_SERVER=root@1.2.3.4}"
APP_DIR="/opt/lingguang-api"
SERVICE="lingguang-api"
HEALTH_URL="https://duyuxiang.cn/api/v2/health"
PIP_MIRROR="https://mirrors.aliyun.com/pypi/simple/"
TARBALL="/tmp/lingguang-deploy.tar.gz"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== 1/5 本地打包（排除 venv/.git/__pycache__）==="
cd "$PROJECT_DIR"
tar --exclude=venv --exclude=.git \
    --exclude='__pycache__' --exclude=.pytest_cache \
    -czf "$TARBALL" .
echo "打包完成: $(ls -lh "$TARBALL" | awk '{print $5}')"

echo "=== 2/5 上传到 $SERVER ==="
scp -q "$TARBALL" "$SERVER":/tmp/
echo "上传完成"

echo "=== 3/5 服务器解压并安装依赖（阿里云镜像）==="
ssh "$SERVER" "set -e
cd $APP_DIR
tar -xzf /tmp/lingguang-deploy.tar.gz 2>/dev/null
rm -f /tmp/lingguang-deploy.tar.gz
./venv/bin/pip install -r requirements.txt -i $PIP_MIRROR --quiet 2>&1 | grep -v 'WARNING' || true
echo '依赖安装完成'"

echo "=== 4/5 重启服务 ==="
ssh "$SERVER" "systemctl restart $SERVICE && sleep 3 && systemctl is-active $SERVICE"

echo "=== 5/5 健康检查 ==="
rm -f "$TARBALL"
for i in 1 2 3 4 5; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$HEALTH_URL" || true)
  if [ "$CODE" = "200" ]; then
    echo "✅ 发布成功: $HEALTH_URL => 200"
    exit 0
  fi
  echo "第 $i 次检查返回 $CODE，2 秒后重试..."
  sleep 2
done
echo "❌ 健康检查失败（$HEALTH_URL），请登录服务器排查: journalctl -u $SERVICE -n 50"
exit 1
