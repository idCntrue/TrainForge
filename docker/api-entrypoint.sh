#!/bin/sh
set -eu

yolo-factory init-storage --system "$YOLO_FACTORY_SYSTEM_CONFIG" >/dev/null
mkdir -p "$YOLO_FACTORY_TASK_CONFIG_DIR"

exec "$@"
