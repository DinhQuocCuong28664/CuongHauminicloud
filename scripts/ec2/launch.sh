#!/usr/bin/env bash
# launch.sh — tạo hạ tầng EC2 cho MyMiniCloud ở tài khoản B (profile default, ap-southeast-1):
# key pair, security group, instance t3.medium Ubuntu 24.04 (gp3 30 GB). Chạy lại được:
# tài nguyên đã có thì dùng lại. Ghi ID và địa chỉ vào scripts/ec2/instance.env (không commit).
#   bash scripts/ec2/launch.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")"

aws_() { aws --profile default --region ap-southeast-1 "$@" | tr -d '\r'; }

NAME=MyMiniCloud-523H0008-523H0025
PROJECT=minicloud-523H0008-523H0025
KEY=minicloud-523h0008-523h0025-key
SG_NAME=MiniCloud-SG-523H0008-523H0025
TYPE=t3.medium
MYIP="$(curl -s https://checkip.amazonaws.com | tr -d '\r\n')/32"

echo "Tài khoản: $(aws_ sts get-caller-identity --query Account --output text) | IP của bạn: $MYIP"

VPC=$(aws_ ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
AMI=$(aws_ ssm get-parameter --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
        --query Parameter.Value --output text)
echo "VPC mặc định: $VPC | AMI Ubuntu 24.04: $AMI"

# ---------- Key pair (ED25519, file .pem chỉ lưu trên máy này) ----------
if [ ! -s "$KEY.pem" ]; then
  aws_ ec2 create-key-pair --key-name "$KEY" --key-type ed25519 --key-format pem \
    --tag-specifications "ResourceType=key-pair,Tags=[{Key=Project,Value=$PROJECT}]" \
    --query KeyMaterial --output text > "$KEY.pem"
  chmod 600 "$KEY.pem"
  echo "Đã tạo key pair $KEY"
fi

# ---------- Security group ----------
SG=$(aws_ ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC" \
       --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG" = "None" ]; then
  SG=$(aws_ ec2 create-security-group --group-name "$SG_NAME" --vpc-id "$VPC" \
         --description "MyMiniCloud 523H0008-523H0025: proxy public, cac cong quan tri chi My IP" \
         --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=$SG_NAME},{Key=Project,Value=$PROJECT}]" \
         --query GroupId --output text)
  # 80 (reverse proxy) mở cho mọi người để giảng viên xem; SSH và cổng quản trị chỉ My IP.
  # Không mở 3306 (DB), 9100 (node-exporter), 1053/udp (DNS).
  perms="[{\"IpProtocol\":\"tcp\",\"FromPort\":80,\"ToPort\":80,\"IpRanges\":[{\"CidrIp\":\"0.0.0.0/0\",\"Description\":\"Reverse proxy\"}]}"
  for p in "22:SSH" "8080:Web1" "8088:Web2" "8085:App" "8081:Keycloak" "9000:MinIO API" "9001:MinIO Console" "9090:Prometheus" "3000:Grafana"; do
    port=${p%%:*}; desc=${p#*:}
    perms="$perms,{\"IpProtocol\":\"tcp\",\"FromPort\":$port,\"ToPort\":$port,\"IpRanges\":[{\"CidrIp\":\"$MYIP\",\"Description\":\"$desc - My IP\"}]}"
  done
  aws_ ec2 authorize-security-group-ingress --group-id "$SG" --ip-permissions "$perms]" >/dev/null
  echo "Đã tạo security group $SG_NAME ($SG)"
fi

# Nâng cao: thêm luật còn thiếu vào security group đã có (chạy lại không sao: luật trùng bị bỏ qua).
# 443 (HTTPS của proxy) mở cho mọi người; 9093 (Alertmanager) và các cổng quản trị chỉ cho IP hiện tại của bạn
ensure_rule() {   # ensure_rule <cổng> <CIDR> <mô tả>
  out=$(aws --profile default --region ap-southeast-1 ec2 authorize-security-group-ingress --group-id "$SG" \
        --ip-permissions "[{\"IpProtocol\":\"tcp\",\"FromPort\":$1,\"ToPort\":$1,\"IpRanges\":[{\"CidrIp\":\"$2\",\"Description\":\"$3\"}]}]" 2>&1) \
    && echo "  + $1 $2 ($3)" || { echo "$out" | grep -q Duplicate || echo "$out"; }
}
echo "Kiểm tra luật của $SG"
ensure_rule 443 0.0.0.0/0 "HTTPS reverse proxy"
for p in "22:SSH" "8080:Web1" "8088:Web2" "8085:App" "8081:Keycloak" "9000:MinIO API" "9001:MinIO Console" \
         "9090:Prometheus" "3000:Grafana" "9093:Alertmanager"; do
  ensure_rule "${p%%:*}" "$MYIP" "${p#*:} - My IP"
done

# ---------- Instance ----------
IID=$(aws_ ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" \
        "Name=instance-state-name,Values=pending,running,stopping,stopped" \
        --query 'Reservations[0].Instances[0].InstanceId' --output text)
if [ "$IID" = "None" ]; then
  IID=$(aws_ ec2 run-instances --image-id "$AMI" --instance-type "$TYPE" --key-name "$KEY" \
          --security-group-ids "$SG" \
          --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":30,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
          --metadata-options HttpTokens=required,HttpEndpoint=enabled \
          --user-data "file://$(cygpath -m "$PWD/user-data.sh")" \
          --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME},{Key=Project,Value=$PROJECT}]" \
                               "ResourceType=volume,Tags=[{Key=Name,Value=$NAME-root},{Key=Project,Value=$PROJECT}]" \
          --query 'Instances[0].InstanceId' --output text)
  echo "Đã tạo instance $IID ($TYPE)"
else
  state=$(aws_ ec2 describe-instances --instance-ids "$IID" --query 'Reservations[0].Instances[0].State.Name' --output text)
  [ "$state" = "stopped" ] && aws_ ec2 start-instances --instance-ids "$IID" >/dev/null && echo "Bật lại instance $IID"
fi

aws_ ec2 wait instance-running --instance-ids "$IID"
read -r IP DNS < <(aws_ ec2 describe-instances --instance-ids "$IID" \
  --query 'Reservations[0].Instances[0].[PublicIpAddress,PublicDnsName]' --output text)

cat > instance.env <<EOF
INSTANCE_ID=$IID
SG_ID=$SG
KEY_FILE=$KEY.pem
PUBLIC_IP=$IP
PUBLIC_DNS=$DNS
EOF
echo "Instance $IID running | public IP $IP | $DNS"
