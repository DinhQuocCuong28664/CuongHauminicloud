#!/bin/bash
# user-data.sh — cloud-init runs it once on the first boot of the Ubuntu 24.04 EC2 instance:
# add 2 GB of swap, install Docker Engine + the Compose plugin from the official Docker repository.
set -euxo pipefail

hostnamectl set-hostname minicloud-ec2

# 2 GB of swap in case Keycloak (JVM) needs more memory on the 4 GB machine
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Docker Engine per the official guide (https://docs.docker.com/engine/install/ubuntu/)
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
