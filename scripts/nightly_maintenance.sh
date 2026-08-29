#!/bin/bash
# Nightly maintenance for the /demo/ demonstrators, implementing the design in
# docs/website-generation.md ("Nightly maintenance"):
#   1. Generation — regenerate demonstrator pages from their live sources.
#   2. Curation checks — carried inside the generators (Curation section).
#   3. AI assessment — an LLM pass over the curation output and the diff since
#      the previous run, published beside the generated pages.
#
# Runs from the admin crontab (host time is UTC); state and staging live in
# ~/.epic-web-demo/. The live page is replaced only after a successful
# generator run; an AI-step failure leaves the pages current and publishes a
# report page stating the failure.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST=/var/www/epic-devcloud-landing/demo
STATE="$HOME/.epic-web-demo"
CLAUDE="$HOME/.local/bin/claude"
mkdir -p "$STATE" "$DEST/documents"

echo "=== nightly maintenance $(date -u '+%Y-%m-%d %H:%M:%SZ')"

# --- 1. Generation: build to staging, install only on success -------------
NEW="$STATE/documents.new.html"
if ! python3 "$REPO/documents/zenodo_documents.py" --out "$NEW"; then
    echo "ERROR: generator failed (rc=$?); live page left untouched"
    exit 1
fi

LIVE="$DEST/documents/index.html"
PREV="$STATE/documents.prev.html"
[ -f "$LIVE" ] && cp "$LIVE" "$PREV"

DIFF="$STATE/documents.diff"
if [ -f "$PREV" ]; then
    diff -u "$PREV" "$NEW" > "$DIFF" || true
else
    echo "no previous page recorded: first run" > "$DIFF"
fi
cp "$NEW" "$LIVE"
echo "installed documents page: $(wc -c < "$LIVE") bytes, overnight diff $(wc -l < "$DIFF") lines"

# --- 2. Curation output, extracted as text for the assessment -------------
CURATION="$STATE/curation.txt"
python3 - "$LIVE" > "$CURATION" <<'PYEOF'
import html, re, sys
page = open(sys.argv[1], encoding='utf-8').read()
m = re.search(r'<section id="curation".*?</section>', page, re.S)
if not m:
    print("No curation section in the generated page (no issues found).")
else:
    text = re.sub(r'<li[^>]*>', '\n- ', m.group(0))
    text = re.sub(r'<h2[^>]*>', '\n## ', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    print(html.unescape(re.sub(r'[ \t]+', ' ', text)).strip())
PYEOF
echo "curation output: $(wc -l < "$CURATION") lines"

# --- 3. AI assessment ------------------------------------------------------
REPORT="$DEST/documents/maintenance.html"
PROMPT="$STATE/prompt.txt"
RAW="$STATE/report.raw"
{
    cat <<'EOF'
Write the nightly maintainer report for the generated ePIC documents page
(https://epic-devcloud.org/demo/documents/, built from the ePIC community on
Zenodo). Inputs below: the page's curation output (programmatic checks), and
the unified diff of the page since the previous nightly run.

The report is for a human curator. Cover, briefly and concretely:
- proposed document categories for records the checks list as unclassified
- drafted keyword and metadata fixes a curator could apply in Zenodo
- notable changes in the document corpus since the previous run (from the
  diff; if the diff says first run, say the baseline is being established)
Ground every claim in the inputs; do not invent records or issues.

Output: one complete self-contained HTML page, nothing before <!DOCTYPE html>
and nothing after </html>. Title "ePIC documents nightly report". Plain
readable styling, respectful of prefers-color-scheme, no external assets.
Include the generation timestamp (UTC) in the page body.
EOF
    echo
    echo "Generation timestamp: $(date -u '+%Y-%m-%d %H:%M UTC')"
    echo
    echo "--- CURATION OUTPUT ---"
    cat "$CURATION"
    echo
    echo "--- DIFF SINCE PREVIOUS RUN (unified, truncated at 40000 bytes) ---"
    head -c 40000 "$DIFF"
} > "$PROMPT"

if timeout 600 "$CLAUDE" -p --output-format text < "$PROMPT" > "$RAW" 2>"$STATE/claude.err"; then
    # Publish the HTML document, tolerating a fenced or prefixed reply.
    python3 - "$RAW" "$REPORT" <<'PYEOF'
import re, sys
raw = open(sys.argv[1], encoding='utf-8').read()
m = re.search(r'<!DOCTYPE html.*</html>', raw, re.S | re.I)
if m:
    out = m.group(0)
else:
    import html
    out = ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
           "<title>ePIC documents nightly report</title></head><body><pre>"
           + html.escape(raw) + "</pre></body></html>")
open(sys.argv[2], 'w', encoding='utf-8').write(out + "\n")
PYEOF
    echo "assessment published: $REPORT ($(wc -c < "$REPORT") bytes)"
else
    rc=$?
    echo "ERROR: claude assessment failed (rc=$rc); publishing failure notice"
    sed -n '1,5p' "$STATE/claude.err"
    cat > "$REPORT" <<EOF
<!DOCTYPE html><html><head><meta charset="utf-8">
<title>ePIC documents nightly report</title></head><body>
<h1>ePIC documents nightly report</h1>
<p>The AI assessment step failed on $(date -u '+%Y-%m-%d %H:%M UTC')
(exit $rc). The generated pages themselves are current; see the
<a href="/demo/documents/">documents page</a> and its Curation section.</p>
</body></html>
EOF
fi

echo "=== done $(date -u '+%Y-%m-%d %H:%M:%SZ')"
