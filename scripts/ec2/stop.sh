#!/usr/bin/env bash
# stop.sh — Stop (không Terminate) instance EC2 của MyMiniCloud để ngừng tính tiền giờ máy.
# Ổ EBS 30 GB vẫn giữ (vẫn tính phí lưu trữ nhỏ); public IP được trả lại và sẽ đổi khi Start lại.
#   bash scripts/ec2/stop.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")"
. ./instance.env
aws_() { aws --profile default --region ap-southeast-1 "$@" | tr -d '\r'; }

aws_ ec2 stop-instances --instance-ids "$INSTANCE_ID" --query 'StoppingInstances[0].[InstanceId,PreviousState.Name,CurrentState.Name]' --output text
aws_ ec2 wait instance-stopped --instance-ids "$INSTANCE_ID"
aws_ ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].[InstanceId,InstanceType,State.Name]' --output text
