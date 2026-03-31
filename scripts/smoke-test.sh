#!/usr/bin/env bash
# =============================================================================
# smoke-test.sh — Build & run gemini-webui from local source in a test container
#
# Usage:
#   ./scripts/smoke-test.sh [--no-stop] [--port PORT] [--tag TAG] [--help]
#
# Behaviour:
#   1. Inspects gemini-webui-dev to extract port, env vars, and volume name.
#      Falls back to safe defaults if the container doesn't exist.
#   2. Builds a fresh image from the current working tree with docker buildx.
#   3. Stops gemini-webui-dev (unless --no-stop) and starts the test container
#      on the same port with the same volume and env vars.
#   4. Tails logs until Ctrl-C, then offers to remove the test container.
# =============================================================================
set -euo pipefail

# ─── Tuneable defaults ───────────────────────────────────────────────────────
DEV_CONTAINER="${DEV_CONTAINER:-gemini-webui-dev}"
TEST_CONTAINER="${TEST_CONTAINER:-gemini-webui-smoke}"
IMAGE_TAG="${IMAGE_TAG:-gemini-webui:smoke-local}"
DEFAULT_PORT="${DEFAULT_PORT:-5000}"
BYPASS_AUTH="${BYPASS_AUTH:-true}"        # set false to test real auth
PLATFORM="${PLATFORM:-linux/$(uname -m | sed 's/aarch64/arm64/;s/x86_64/amd64/')}"
# ─────────────────────────────────────────────────────────────────────────────

NO_STOP=false
OVERRIDE_PORT=""

usage() {
  grep '^#' "$0" | grep -v '#!/' | sed 's/^# \{0,2\}//'
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-stop)   NO_STOP=true ;;
    --port)      OVERRIDE_PORT="$2"; shift ;;
    --tag)       IMAGE_TAG="$2"; shift ;;
    --help|-h)   usage ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
  shift
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "📁  Repo root : $REPO_ROOT"

# ─── Step 1: Probe gemini-webui-dev ──────────────────────────────────────────
echo ""
echo "🔍  Probing '$DEV_CONTAINER'..."

if docker inspect "$DEV_CONTAINER" &>/dev/null; then
  HAS_DEV=true

  # Extract host port (first published port)
  HOST_PORT="$(docker inspect "$DEV_CONTAINER" \
    --format '{{range $p,$b := .HostConfig.PortBindings}}{{range $b}}{{.HostPort}}{{end}}{{end}}' \
    | head -1)"
  HOST_PORT="${HOST_PORT:-$DEFAULT_PORT}"

  # Extract volume name (first volume mount destination path & name)
  VOLUME_NAME="$(docker inspect "$DEV_CONTAINER" \
    --format '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}{{end}}{{end}}' \
    | head -1)"

  # Extract env vars (skip PATH and internal Python vars we don't want to copy)
  SKIP_VARS="^PATH=|^LANG=|^GPG_KEY=|^PYTHON_"
  mapfile -t ENV_VARS < <(docker inspect "$DEV_CONTAINER" \
    --format '{{range .Config.Env}}{{.}}\n{{end}}' \
    | grep -Ev "$SKIP_VARS" | grep -v '^$')

  # Extract network name
  NETWORK="$(docker inspect "$DEV_CONTAINER" \
    --format '{{range $k,$_ := .NetworkSettings.Networks}}{{$k}}{{end}}' \
    | head -1)"

  echo "   ✅ Found container — port=$HOST_PORT, volume=$VOLUME_NAME, network=$NETWORK"
else
  HAS_DEV=false
  HOST_PORT="$DEFAULT_PORT"
  VOLUME_NAME=""
  ENV_VARS=()
  NETWORK=""
  echo "   ⚠️  '$DEV_CONTAINER' not found — using defaults (port=$HOST_PORT)"
fi

# Override port if user passed --port
[[ -n "$OVERRIDE_PORT" ]] && HOST_PORT="$OVERRIDE_PORT"

# ─── Step 2: Build image from source ─────────────────────────────────────────
echo ""
echo "🔨  Building image '$IMAGE_TAG' from $REPO_ROOT ..."
docker buildx build \
  --platform "$PLATFORM" \
  --tag "$IMAGE_TAG" \
  --load \
  "$REPO_ROOT"

echo "   ✅ Build complete"

# ─── Step 3: Stop dev container (take over its port + volume) ────────────────
if [[ "$HAS_DEV" == true && "$NO_STOP" == false ]]; then
  echo ""
  echo "⏹️   Stopping '$DEV_CONTAINER' (use --no-stop to skip)..."
  docker stop "$DEV_CONTAINER" 2>/dev/null && echo "   ✅ Stopped" || echo "   ℹ️  Already stopped"
fi

# ─── Step 4: Remove stale test container if present ──────────────────────────
if docker inspect "$TEST_CONTAINER" &>/dev/null; then
  echo ""
  echo "🗑️   Removing stale '$TEST_CONTAINER'..."
  docker rm -f "$TEST_CONTAINER" >/dev/null
fi

# ─── Step 5: Assemble docker run args ────────────────────────────────────────
RUN_ARGS=(
  "--name" "$TEST_CONTAINER"
  "--rm"                          # auto-remove on exit — clean smoke test
  "-p" "${HOST_PORT}:5000"
  "-e" "BYPASS_AUTH_FOR_TESTING=$BYPASS_AUTH"
  "-e" "FLASK_USE_RELOADER=false"
  "-e" "PORT=5000"
)

# Re-attach volume if we found one
if [[ -n "$VOLUME_NAME" ]]; then
  RUN_ARGS+=("-v" "${VOLUME_NAME}:/data")
fi

# Re-apply env vars from the dev container
for var in "${ENV_VARS[@]}"; do
  RUN_ARGS+=("-e" "$var")
done

# Re-attach network if we found one (enables service discovery within compose stack)
if [[ -n "$NETWORK" ]]; then
  RUN_ARGS+=("--network" "$NETWORK")
fi

# ─── Step 6: Run ─────────────────────────────────────────────────────────────
echo ""
echo "🚀  Starting '$TEST_CONTAINER' on port $HOST_PORT ..."
echo "    docker run ${RUN_ARGS[*]} $IMAGE_TAG"
echo ""
echo "    App → http://localhost:${HOST_PORT}"
echo "    Ctrl-C to stop"
echo ""

cleanup() {
  echo ""
  echo "🛑  Caught Ctrl-C. Stopping '$TEST_CONTAINER'..."
  docker stop "$TEST_CONTAINER" 2>/dev/null || true

  if [[ "$HAS_DEV" == true && "$NO_STOP" == false ]]; then
    echo "▶️   Restarting '$DEV_CONTAINER'..."
    docker start "$DEV_CONTAINER" 2>/dev/null || true
  fi
  echo "Done."
  exit 0
}
trap cleanup INT TERM

docker run "${RUN_ARGS[@]}" "$IMAGE_TAG"
