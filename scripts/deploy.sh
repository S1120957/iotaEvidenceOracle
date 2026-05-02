#!/usr/bin/env bash
# deploy.sh — Build and publish Design A and Design B packages.
# Usage: bash scripts/deploy.sh [localnet|testnet]
# Appends PACKAGE_ID_A and PACKAGE_ID_B to .env.

set -euo pipefail

ENV=${1:-localnet}
iota client switch --env "$ENV"

echo "Building and publishing Design A..."
PUBLISH_A=$(iota client publish \
    --path contracts/design_a \
    --gas-budget 200000000 \
    --json 2>&1)

PACKAGE_ID_A=$(echo "$PUBLISH_A" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); \
      print(next(e['packageId'] for e in d['objectChanges'] \
      if e['type']=='published'))" 2>/dev/null \
    || echo "$PUBLISH_A" | grep -oE '"packageId":"0x[0-9a-f]+"' \
    | head -1 | grep -oE '0x[0-9a-f]+')

echo "  Design A package ID: $PACKAGE_ID_A"

echo "Building and publishing Design B..."
PUBLISH_B=$(iota client publish \
    --path contracts/design_b \
    --gas-budget 200000000 \
    --json 2>&1)

PACKAGE_ID_B=$(echo "$PUBLISH_B" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); \
      print(next(e['packageId'] for e in d['objectChanges'] \
      if e['type']=='published'))" 2>/dev/null \
    || echo "$PUBLISH_B" | grep -oE '"packageId":"0x[0-9a-f]+"' \
    | head -1 | grep -oE '0x[0-9a-f]+')

echo "  Design B package ID: $PACKAGE_ID_B"

# Append to .env
{
    echo "PACKAGE_ID_A=$PACKAGE_ID_A"
    echo "PACKAGE_ID_B=$PACKAGE_ID_B"
} >> .env

echo "Package IDs written to .env"
echo ""
echo "Next: run Move unit tests"
echo "  iota move test --path contracts/design_a"
echo "  iota move test --path contracts/design_b"
