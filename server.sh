#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

HOST="0.0.0.0"
PORT="8118"
PID_FILE="$ROOT/.server.pid"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/server.log"

stop_server() {
  if [[ -f "$PID_FILE" ]]; then
    local old_pid
    old_pid="$(cat "$PID_FILE")"
    if kill -0 "$old_pid" 2>/dev/null; then
      echo "停止旧进程 (pid $old_pid)..."
      kill "$old_pid" 2>/dev/null || true
      sleep 1
      if kill -0 "$old_pid" 2>/dev/null; then
        kill -9 "$old_pid" 2>/dev/null || true
      fi
    fi
    rm -f "$PID_FILE"
  fi

  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -ti ":$PORT" 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      echo "释放端口 $PORT..."
      # shellcheck disable=SC2086
      kill $pids 2>/dev/null || true
      sleep 1
    fi
  fi
}

start_server() {
  if [[ ! -x "$ROOT/.venv/bin/uvicorn" ]]; then
    echo "虚拟环境未就绪，请先执行: ./setup_venv.sh" >&2
    exit 1
  fi

  mkdir -p "$LOG_DIR"
  stop_server

  echo "启动服务: http://$HOST:$PORT"
  nohup "$ROOT/.venv/bin/uvicorn" app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    >>"$LOG_FILE" 2>&1 &

  echo $! >"$PID_FILE"
  sleep 1

  if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "已启动 (pid $(cat "$PID_FILE"))，日志: $LOG_FILE"
  else
    echo "启动失败，请查看日志: $LOG_FILE" >&2
    exit 1
  fi
}

case "${1:-restart}" in
  start)
    start_server
    ;;
  stop)
    stop_server
    echo "已停止"
    ;;
  restart|*)
    start_server
    ;;
esac
