#!/bin/bash
# Deploy the /demo/ area: copy static files and regenerate demonstrator pages.
# Serves from the epic-devcloud.org landing document root; no Apache change
# and no service reload involved.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST=/var/www/epic-devcloud-landing/demo

mkdir -p "$DEST/documents"

cp "$REPO/site/index.html" "$DEST/index.html"

python3 "$REPO/documents/zenodo_documents.py" --out "$DEST/documents/index.html"

echo "Deployed /demo/ to $DEST"
