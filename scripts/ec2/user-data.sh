#!/bin/bash
# user-data.sh — cloud-init chạy một lần khi EC2 Ubuntu 24.04 khởi động lần đầu:
# thêm swap 2 GB, cài Docker Engine + Compose plugin từ repo chính thức của Docker.
set -euxo pipefail

hostnamectl set-hostname minicloud-ec2

# Swap 2 GB phòng khi Keycloak (JVM) cần thêm bộ nhớ trên máy 4 GB
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Docker Engine theo hướng dẫn chính thức (https://docs.docker.com/engine/install/ubuntu/)
apt-get update
apt-get install -y ca-certificates curl bind9-dnsutils python3
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
usermod -aG docker ubuntu

echo "MyMiniCloud user-data finished" > /var/log/minicloud-user-data.done
