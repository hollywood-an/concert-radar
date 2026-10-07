#!/usr/bin/env bash
# Regenerate the Python code for proto/ in every service that speaks it, using the
# recommender's pinned grpcio-tools and mypy-protobuf. CI reruns this and fails if the
# committed code differs.
set -euo pipefail
cd "$(dirname "$0")/.."

PROTOS=(recommender/v1/recommender.proto)

for service in recommender gateway; do
  out="services/$service"
  rm -rf "$out/src/gen"
  # Map proto/ to the virtual root src/gen so protoc writes the code to src/gen/... and
  # the generated imports read `from src.gen.recommender.v1 import ...`, which is how
  # the services import their own modules.
  uv run --quiet --project services/recommender python -m grpc_tools.protoc \
    -Isrc/gen=proto \
    --python_out="$out" --grpc_python_out="$out" \
    --mypy_out=quiet:"$out" --mypy_grpc_out=quiet:"$out" \
    "${PROTOS[@]/#/src/gen/}"
  find "$out/src/gen" -type d -exec touch {}/__init__.py \;
done
