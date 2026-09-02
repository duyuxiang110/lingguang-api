#!/bin/bash
set -e

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
apt-get install -y python3 python3-pip python3-venv \
    libreoffice libreoffice-writer \
    poppler-utils \
    libgl1-mesa-glx libglib2.0-0 \
    fonts-noto-cjk fonts-wqy-zenhei

echo "=== 3. 创建应用目录 ==="
mkdir -p /opt/lingguang-api
mkdir -p /tmp/lingguang/{uploads,work,output}
chown -R www-data:www-data /tmp/lingguang

echo "=== 4. 部署代码 ==="
cd /opt/lingguang-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "=== 5. 安装 systemd 服务 ==="
cp lingguang-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable lingguang-api

echo "=== 6. 配置 crontab 清理临时文件 ==="
(crontab -l 2>/dev/null; echo '0 * * * * find /tmp/lingguang -mindepth 1 -mmin +60 -delete') | crontab -

echo "=== 完成 ==="
echo "请手动检查 Nginx 配置和启动服务: systemctl start lingguang-api"
