#!/bin/sh
set -eu

PACKAGE=${1:-}
PROJECT_DIR=${2:-/opt/yolo_model_factory}

test -n "$PACKAGE" || { echo "Usage: $0 PACKAGE [PROJECT_DIR]" >&2; exit 2; }
test -f "$PACKAGE" || { echo "Package not found: $PACKAGE" >&2; exit 2; }
test -d "$PROJECT_DIR" || { echo "Project directory not found: $PROJECT_DIR" >&2; exit 2; }
test -f "$PROJECT_DIR/.env" || { echo "Live environment file not found: $PROJECT_DIR/.env" >&2; exit 2; }

PROJECT_DIR=$(CDPATH= cd -- "$PROJECT_DIR" && pwd)
PROJECT_PARENT=$(dirname -- "$PROJECT_DIR")
PROJECT_NAME=$(basename -- "$PROJECT_DIR")

tar -tzf "$PACKAGE" | while IFS= read -r entry; do
  case "$entry" in
    /*|../*|*/../*|*/..|*\\*)
      echo "Unsafe archive path: $entry" >&2
      exit 3
      ;;
  esac
done

STAGING_ROOT=$(mktemp -d "$PROJECT_PARENT/.yolo-update.XXXXXX")
cleanup() {
  case "$STAGING_ROOT" in
    "$PROJECT_PARENT"/.yolo-update.*)
      test ! -d "$STAGING_ROOT" || rm -rf -- "$STAGING_ROOT"
      ;;
  esac
}
trap cleanup EXIT HUP INT TERM

tar -xzf "$PACKAGE" -C "$STAGING_ROOT"
STAGED_PROJECT=
for compose_file in "$STAGING_ROOT/compose.yaml" "$STAGING_ROOT"/*/compose.yaml; do
  if [ -f "$compose_file" ]; then
    candidate=$(dirname -- "$compose_file")
    if [ -n "$STAGED_PROJECT" ] && [ "$candidate" != "$STAGED_PROJECT" ]; then
      echo "Package contains multiple project roots" >&2
      exit 3
    fi
    STAGED_PROJECT=$candidate
  fi
done

test -n "$STAGED_PROJECT" || { echo "Package does not contain compose.yaml" >&2; exit 3; }
test -f "$STAGED_PROJECT/docker/deploy.sh" || { echo "Package does not contain docker/deploy.sh" >&2; exit 3; }

# The package never supplies runtime configuration. Only the live environment is inherited.
cp "$PROJECT_DIR/.env" "$STAGED_PROJECT/.env"
chmod +x "$STAGED_PROJECT/docker/deploy.sh"
export COMPOSE_PROJECT_NAME=yolo_model_factory
NEW_TAG="package-$(date +%Y%m%d-%H%M%S)"

"$STAGED_PROJECT/docker/deploy.sh" "$NEW_TAG"

BACKUP_DIR="$PROJECT_PARENT/$PROJECT_NAME.source-backup-$(date +%Y%m%d-%H%M%S)"
test ! -e "$BACKUP_DIR" || { echo "Source backup already exists: $BACKUP_DIR" >&2; exit 4; }
mv "$PROJECT_DIR" "$BACKUP_DIR"
if ! mv "$STAGED_PROJECT" "$PROJECT_DIR"; then
  mv "$BACKUP_DIR" "$PROJECT_DIR"
  echo "Source switch failed; original source restored" >&2
  exit 4
fi

echo "Deployment complete: $PROJECT_DIR"
echo "Source backup retained: $BACKUP_DIR"
echo "Runtime data, models, and SQLite database were not replaced."
