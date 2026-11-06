#!/usr/bin/env bash
# push-images.sh — push the four project images with IMAGE_TAG from .env and also as "latest",
# recording every command and its output into evidence/d-docker-push-<tag>.txt.
#   bash scripts/push-images.sh          (run "docker compose build" and "docker compose --profile ops build" first)
set -eu
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

OUT="evidence/d-docker-push-${IMAGE_TAG}.txt"
: > "$OUT"
for name in web app proxy db-backup; do
  repo="${DOCKERHUB_USER}/myminicloud-${name}"
  docker tag "${repo}:${IMAGE_TAG}" "${repo}:latest"
  for tag in "$IMAGE_TAG" latest; do
    echo "\$ docker push ${repo}:${tag}" | tee -a "$OUT"
    docker push "${repo}:${tag}" 2>&1 | grep -vE 'Preparing|Waiting|Layer already exists' | tee -a "$OUT"
  done
done
echo "saved to $OUT"
