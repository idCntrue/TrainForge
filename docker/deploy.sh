#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"

NEW_TAG=${1:-"manual-$(date +%Y%m%d%H%M%S)"}
case "$NEW_TAG" in
  *[!A-Za-z0-9._-]*|'') echo "Invalid image tag: $NEW_TAG" >&2; exit 2 ;;
esac

OLD_API_CONTAINER=$(docker compose ps -q api 2>/dev/null || true)
OLD_API_IMAGE=
if [ -n "$OLD_API_CONTAINER" ]; then
  OLD_API_IMAGE=$(docker inspect --format '{{.Config.Image}}' "$OLD_API_CONTAINER" 2>/dev/null || true)
fi
OLD_TAG=${OLD_API_IMAGE##*:}
if [ -z "$OLD_API_IMAGE" ] || [ "$OLD_TAG" = "$OLD_API_IMAGE" ]; then
  OLD_TAG=latest
fi

persist_tag() {
  tag=$1
  if grep -q '^IMAGE_TAG=' .env 2>/dev/null; then
    sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$tag/" .env
  else
    printf '\nIMAGE_TAG=%s\n' "$tag" >> .env
  fi
}

rollback() {
  echo "Health check failed; rollback to image tag $OLD_TAG" >&2
  export IMAGE_TAG=$OLD_TAG
  persist_tag "$OLD_TAG"
  docker compose up -d --no-build --remove-orphans
}

test -f .env || { echo "Missing $PROJECT_DIR/.env" >&2; exit 2; }
export IMAGE_TAG=$NEW_TAG
docker compose config --quiet

echo "Building Docker images with tag $NEW_TAG"
docker compose build

if docker compose ps --status running --services 2>/dev/null | grep -qx api; then
  backup_name="factory.pre-deploy-$(date +%Y%m%d-%H%M%S).db"
  docker compose exec -T api python3.10 -c \
    "import sqlite3; src=sqlite3.connect('/data/registry/factory.db'); dst=sqlite3.connect('/data/registry/$backup_name'); src.backup(dst); dst.close(); src.close()"
  echo "SQLite backup created: /data/registry/$backup_name"
fi

docker compose up -d --no-build --remove-orphans

WEB_PORT=$(sed -n 's/^WEB_PORT=//p' .env | tail -n 1)
WEB_PORT=${WEB_PORT:-8080}
attempt=0
while [ "$attempt" -lt 60 ]; do
  if curl --fail --silent "http://127.0.0.1:$WEB_PORT/api/health" >/dev/null; then
    persist_tag "$NEW_TAG"
    echo "Deployment healthy: image tag $NEW_TAG, port $WEB_PORT"
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 2
done

rollback
exit 1
