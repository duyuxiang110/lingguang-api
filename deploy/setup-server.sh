#!/bin/bash
set -e

REPO_URL="https://github.com/duyuxiang110/lingguang-api.git"
APP_DIR="/opt/lingguang-api"

echo "=== 1. 创建 2GB swap ==="
if ! swapon --show | grep -q swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q swapfile /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "Swap 已创建"
else
  echo "Swap 已存在"
fi

echo "=== 2. 安装系统依赖 ==="
apt-get update
apt-get install -y git python3 python3-pip python3-venv \
    libreoffice libreoffice-writer \
    poppler-utils \
    libgl1-mesa-glx libglib2.0-0 \
    fonts-noto-cjk fonts-wqy-zenhei

echo "=== 3. 拉取代码 ==="
if [ -d "$APP_DIR/.git" ]; then
  cd "$APP_DIR"
  git pull origin main
  echo "代码已更新"
else
  rm -rf "$APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
  cd "$APP_DIR"
  echo "代码已克隆"
fi

echo "=== 4. 创建临时目录 ==="
mkdir -p /tmp/lingguang/{uploads,work,output}
chown -R www-data:www-data /tmp/lingguang

echo "=== 5. 创建虚拟环境并安装依赖 ==="
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== 6. 安装 systemd 服务 ==="
cp "$APP_DIR/lingguang-api.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable lingguang-api

echo "=== 7. 配置 crontab 清理临时文件 ==="
(crontab -l 2>/dev/null | grep -v 'find /tmp/lingguang'; echo '0 * * * * find /tmp/lingguang -mindepth 1 -mmin +60 -delete') | crontab -

echo "=== 8. 配置 Nginx ==="
NGINX_CONF=""
for f in /etc/nginx/conf.d/lingguang.conf /etc/nginx/sites-available/lingguang; do
  if [ -f "$f" ]; then
    NGINX_CONF="$f"
    break
  fi
done
if [ -n "$NGINX_CONF" ]; then
  if grep -q '/api/v2/' "$NGINX_CONF"; then
    echo "Nginx 已有 /api/v2/ 配置"
  else
    # 在 server 块末尾的 gzip 之前插入 /api/v2/ location
    sed -i '/gzip on;/i\    location /api/v2/ {\n        proxy_pass http://127.0.0.1:8000;\n        proxy_set_header Host $host;\n        proxy_set_header X-Real-IP $remote_addr;\n        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n        client_max_body_size 60M;\n        proxy_read_timeout 120s;\n        proxy_send_timeout 120s;\n        proxy_buffering off;\n    }\n' "$NGINX_CONF"
    echo "已添加 /api/v2/ 配置到 $NGINX_CONF"
  fi
  nginx -t && nginx -s reload
else
  echo "警告: 未找到 $NGINX_CONF，请手动配置 Nginx"
  echo "需要添加以下 location 块到 server 配置中:"
  echo '    location /api/v2/ {'
  echo '        proxy_pass http://127.0.0.1:8000;'
  echo '        proxy_set_header Host $host;'
  echo '        proxy_set_header X-Real-IP $remote_addr;'
  echo '        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;'
  echo '        client_max_body_size 60M;'
  echo '        proxy_read_timeout 120s;'
  echo '        proxy_send_timeout 120s;'
  echo '        proxy_buffering off;'
  echo '    }'
fi

echo "=== 9. 启动服务 ==="
systemctl restart lingguang-api
sleep 2
systemctl status lingguang-api --no-pager || true

echo "=== 完成 ==="
echo "服务已启动，测试: curl http://127.0.0.1:8000/docs"
