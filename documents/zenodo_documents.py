"""Generate a static ePIC document list page from the Zenodo 'epic' community.

Fetches every record in the community via the public Zenodo REST API,
classifies records into document categories (note ID in title, then
keywords, then Zenodo resource type), and writes a single self-contained
HTML page. No authentication, no dependencies beyond the standard library.

Usage:
    python documents/zenodo_documents.py --out /var/www/epic-devcloud-landing/demo/documents/index.html

Demonstrator for generating the epic-eic.org document pages from Zenodo
instead of maintaining them by hand: the same script run offline can
commit its output to the github-pages repository.
"""

import argparse
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone

API = 'https://zenodo.org/api/records'
PAGE_SIZE = 25  # unauthenticated Zenodo API maximum

NOTE_ID_RE = re.compile(r'epic-(AN|TN|SN)-[A-Za-z]+-\d{4}-\d+', re.IGNORECASE)

# Hand-maintained document pages cross-checked against the community.
CROSSCHECK_PAGES = [
    'https://www.epic-eic.org/documents/analysis_notes.html',
    'https://www.epic-eic.org/documents/reports.html',
]
ZENODO_LINK_RE = re.compile(r'(?:zenodo\.org/records?/|doi\.org/10\.5281/zenodo\.)(\d+)')

# (section key, heading) in display order
SECTIONS = [
    ('analysis-notes', 'Analysis Notes'),
    ('technical-notes', 'Technical Notes'),
    ('reports', 'Reports'),
    ('papers', 'Papers & Proceedings'),
    ('theses', 'Theses'),
    ('presentations', 'Presentations & Posters'),
    ('figures', 'Figures & Images'),
    ('other', 'Other Documents'),
]

RESOURCE_TYPE_SECTION = {
    'Technical note': 'technical-notes',
    'Report': 'reports',
    'Thesis': 'theses',
    'Publication': 'papers',
    'Preprint': 'papers',
    'Conference paper': 'papers',
    'Conference proceeding': 'papers',
    'Journal article': 'papers',
    'Working paper': 'papers',
    'Presentation': 'presentations',
    'Poster': 'presentations',
    'Photo': 'figures',
    'Image': 'figures',
    'Plot': 'figures',
    'Diagram': 'figures',
    'Drawing': 'figures',
    'Figure': 'figures',
}


def fetch_records(community):
    """Fetch all records in the community, paginating. Raises on HTTP/parse errors."""
    records = []
    page = 1
    while True:
        url = f'{API}?communities={community}&size={PAGE_SIZE}&page={page}'
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = json.load(resp)
        except Exception as e:
            raise RuntimeError(f'Zenodo fetch failed ({url}): {e}') from e
        hits = data.get('hits', {}).get('hits', [])
        total = data.get('hits', {}).get('total', 0)
        records.extend(hits)
        if not hits or len(records) >= total:
            break
        page += 1
    if not records:
        raise RuntimeError(f'Zenodo returned no records for community {community!r}')
    return records


def classify(rec):
    """Return the section key for a record."""
    md = rec.get('metadata', {})
    title = md.get('title', '')
    keywords = {k.lower() for k in md.get('keywords', [])}
    m = NOTE_ID_RE.search(title)
    if m:
        kind = m.group(1).upper()
        return 'analysis-notes' if kind == 'AN' else 'technical-notes'
    if 'ana_note' in keywords:
        return 'analysis-notes'
    if 'tech_note' in keywords:
        return 'technical-notes'
    rtype = md.get('resource_type', {}).get('title', '')
    return RESOURCE_TYPE_SECTION.get(rtype, 'other')


def is_template(rec):
    return 'template' in rec.get('metadata', {}).get('title', '').lower()


def record_row(rec, issue):
    md = rec.get('metadata', {})
    return {
        'title': md.get('title', f"record {rec.get('id')}"),
        'url': rec.get('links', {}).get('self_html',
                                       f"https://zenodo.org/records/{rec.get('id')}"),
        'issue': issue,
    }


def metadata_rows(records):
    """Zenodo metadata inconsistencies within the community.

    Checks: template records (excluded from the document sections), note
    records missing their canonical keyword (ana_note / tech_note), and
    note records whose resource type is not 'Technical note' — the only
    Zenodo type appropriate for ePIC notes.
    """
    rows = []
    for rec in records:
        if is_template(rec):
            rows.append(record_row(rec, 'template record (excluded from document counts)'))
            continue
        section = classify(rec)
        if section not in ('analysis-notes', 'technical-notes'):
            continue
        md = rec.get('metadata', {})
        keywords = {k.lower() for k in md.get('keywords', [])}
        expected_kw = 'ana_note' if section == 'analysis-notes' else 'tech_note'
        rec_issues = []
        if expected_kw not in keywords:
            rec_issues.append(f'missing keyword “{expected_kw}”')
        rtype = md.get('resource_type', {}).get('title', '')
        if rtype != 'Technical note':
            rec_issues.append(f'resource type “{rtype}” (expected “Technical note”)')
        if rec_issues:
            rows.append(record_row(rec, '; '.join(rec_issues)))
    return rows


def duplicate_rows(records):
    """Distinct community records sharing a normalized title.

    Scoped to the document categories: presentations, posters, and
    figures legitimately reuse titles across venues.
    """
    doc_sections = {'analysis-notes', 'technical-notes', 'reports', 'papers', 'theses'}
    by_title = {}
    for rec in records:
        if is_template(rec) or classify(rec) not in doc_sections:
            continue
        title = rec.get('metadata', {}).get('title', '')
        norm = NOTE_ID_RE.sub('', title)
        norm = re.sub(r'\s+', ' ', norm).strip(' :').lower()
        if norm:
            by_title.setdefault(norm, []).append(rec)
    rows = []
    for recs in by_title.values():
        if len(recs) > 1:
            first, *rest = sorted(recs, key=lambda r: r.get('id', 0))
            for rec in rest:
                rows.append(record_row(
                    rec, f"possible duplicate of record {first['id']} (same title)"))
    return rows


def crosscheck_rows(records):
    """Cross-check epic-eic.org document pages against the community.

    Flags notes linked from epic-eic.org that are not in the community,
    and links that point at outdated versions of community records. A
    page or record fetch failure is reported as a row, never swallowed.
    """
    ids = {rec.get('id') for rec in records}
    concepts = {rec.get('conceptrecid') for rec in records if rec.get('conceptrecid')}
    rows = []
    seen = set()
    for page_url in CROSSCHECK_PAGES:
        page_name = page_url.rsplit('/', 1)[-1]
        try:
            req = urllib.request.Request(page_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as resp:
                page = resp.read().decode('utf-8', 'replace')
        except Exception as e:
            rows.append({'title': f'Cross-check unavailable: {page_name}',
                         'url': page_url, 'issue': f'page fetch failed: {e}'})
            continue
        for rid in {int(r) for r in ZENODO_LINK_RE.findall(page)}:
            if rid in ids or rid in seen:
                continue
            seen.add(rid)
            try:
                with urllib.request.urlopen(f'{API}/{rid}', timeout=60) as resp:
                    rec = json.load(resp)
            except Exception as e:
                rows.append({'title': f'Zenodo record {rid}',
                             'url': f'https://zenodo.org/records/{rid}',
                             'issue': f'linked from {page_name}; record fetch failed: {e}'})
                continue
            if rec.get('conceptrecid') in concepts:
                issue = (f'epic-eic.org {page_name} links outdated version {rid}; '
                         f'the community holds a newer version')
            else:
                issue = (f'listed on epic-eic.org {page_name} but not in the '
                         f'Zenodo epic community')
            rows.append(record_row(rec, issue))
    return rows


def curation_rows(records):
    return metadata_rows(records) + duplicate_rows(records) + crosscheck_rows(records)


def item_html(rec):
    md = rec.get('metadata', {})
    title = md.get('title', '(untitled)')
    url = rec.get('links', {}).get('self_html', f"https://zenodo.org/records/{rec.get('id')}")
    date = md.get('publication_date', '')
    creators = [c.get('name', '') for c in md.get('creators', [])]
    authors = '; '.join(creators[:3]) + (' et al.' if len(creators) > 3 else '')
    rtype = md.get('resource_type', {}).get('title', '')
    doi = rec.get('doi', '')
    keywords = md.get('keywords', [])
    search_blob = ' '.join([title, authors, rtype, doi, date] + keywords).lower()
    meta_parts = [p for p in [date, authors, rtype] if p]
    doi_link = (f' &middot; <a href="https://doi.org/{html.escape(doi)}">'
                f'{html.escape(doi)}</a>') if doi else ''
    return (
        f'<li class="doc" data-search="{html.escape(search_blob)}">'
        f'<a class="title" href="{html.escape(url)}">{html.escape(title)}</a>'
        f'<div class="meta">{html.escape(" · ".join(meta_parts))}{doi_link}</div>'
        f'</li>'
    )


def curation_item_html(row):
    return (
        f'<li class="doc">'
        f'<a class="title" href="{html.escape(row["url"])}">{html.escape(row["title"])}</a>'
        f'<div class="meta issue">{html.escape(row["issue"])}</div>'
        f'</li>'
    )


def build_page(records, community, issues):
    by_section = {key: [] for key, _ in SECTIONS}
    for rec in records:
        if is_template(rec):
            continue
        by_section[classify(rec)].append(rec)
    for recs in by_section.values():
        recs.sort(key=lambda r: r.get('metadata', {}).get('publication_date', ''), reverse=True)

    toc = []
    sections = []
    for key, heading in SECTIONS:
        recs = by_section[key]
        if not recs:
            continue
        toc.append(f'<a class="toc-link" href="#{key}">{html.escape(heading)} '
                   f'<span class="count">{len(recs)}</span></a>')
        items = '\n'.join(item_html(r) for r in recs)
        sections.append(
            f'<section id="{key}"><h2>{html.escape(heading)} '
            f'<span class="count">{len(recs)}</span></h2>\n'
            f'<ul class="docs">\n{items}\n</ul></section>'
        )

    if issues:
        toc.append(f'<a class="toc-link toc-curation" href="#curation">Curation '
                   f'<span class="count">{len(issues)}</span></a>')
        items = '\n'.join(curation_item_html(row) for row in issues)
        sections.append(
            f'<section id="curation" class="curation"><h2>Curation '
            f'<span class="count">{len(issues)}</span></h2>\n'
            f'<p class="curation-intro">Issues found while generating this page: '
            f'missing <code>ana_note</code>/<code>tech_note</code> keywords, unexpected '
            f'resource types, template records (excluded from the document counts), '
            f'duplicate titles, and a cross-check of the epic-eic.org document pages '
            f'against the community (unregistered notes, outdated version links). '
            f'Fixing these on Zenodo keeps keyword searches and this list complete. '
            f'The section disappears when all checks pass.</p>\n'
            f'<ul class="docs">\n{items}\n</ul></section>'
        )

    generated = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    community_url = f'https://zenodo.org/communities/{community}'
    return PAGE_TEMPLATE.format(
        toc='\n'.join(toc),
        sections='\n'.join(sections),
        total=len(records),
        generated=generated,
        community=html.escape(community),
        community_url=html.escape(community_url),
    )


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ePIC Documents</title>
<style>
  :root {{
    --fg: #333; --bg: #fff; --muted: #666; --link: #2563eb;
    --rule: #e5e7eb; --chip-bg: #eff6ff;
    --warn: #b45309; --warn-chip-bg: #fef3c7;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --fg: #ddd; --bg: #121417; --muted: #9aa3ad; --link: #7aa2f7;
      --rule: #2a2f36; --chip-bg: #1c2430;
      --warn: #fbbf24; --warn-chip-bg: #33260d;
    }}
  }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         max-width: 900px; margin: 40px auto; padding: 0 20px;
         color: var(--fg); background: var(--bg); }}
  h1 {{ font-size: 1.8em; margin-bottom: 0.2em; }}
  h2 {{ font-size: 1.3em; border-bottom: 1px solid var(--rule); padding-bottom: 0.3em;
       margin-top: 1.8em; }}
  a {{ color: var(--link); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .subtitle {{ color: var(--muted); margin-bottom: 1.2em; }}
  .count {{ color: var(--muted); font-weight: normal; font-size: 0.85em; }}
  .toc {{ display: flex; flex-wrap: wrap; gap: 0.6em; margin: 1em 0; }}
  .toc-link {{ background: var(--chip-bg); padding: 0.35em 0.8em; border-radius: 1em;
              font-size: 0.95em; }}
  #filter {{ width: 100%; box-sizing: border-box; font-size: 1em; padding: 0.55em 0.8em;
            margin: 0.5em 0 0.5em; color: var(--fg); background: var(--bg);
            border: 1px solid var(--rule); border-radius: 6px; }}
  ul.docs {{ list-style: none; padding: 0; margin: 0; }}
  li.doc {{ padding: 0.55em 0; border-bottom: 1px solid var(--rule); }}
  li.doc .title {{ font-size: 1.05em; }}
  li.doc .meta {{ color: var(--muted); font-size: 0.92em; margin-top: 0.15em; }}
  .toc-curation {{ background: var(--warn-chip-bg); }}
  section.curation h2 {{ border-bottom-color: var(--warn); }}
  .curation-intro {{ color: var(--muted); font-size: 0.95em; }}
  li.doc .meta.issue {{ color: var(--warn); }}
  footer {{ margin: 3em 0 1em; color: var(--muted); font-size: 0.92em;
           border-top: 1px solid var(--rule); padding-top: 1em; }}
</style>
</head>
<body>
<h1>ePIC Documents</h1>
<p class="subtitle">Generated automatically from the
<a href="{community_url}">ePIC community on Zenodo</a> — {total} records.
No manual maintenance: the list is distilled from Zenodo metadata and can be
regenerated at any time.</p>
<input id="filter" type="search" placeholder="Filter by title, author, keyword, DOI…"
       aria-label="Filter documents">
<nav class="toc">
{toc}
</nav>
{sections}
<footer>Generated {generated} by <code>zenodo_documents.py</code> from Zenodo
community <a href="{community_url}">{community}</a>.
Categories derive from ePIC note IDs, Zenodo keywords, and resource types.</footer>
<script>
  const filter = document.getElementById('filter');
  filter.addEventListener('input', () => {{
    const q = filter.value.trim().toLowerCase();
    document.querySelectorAll('li.doc').forEach(li => {{
      li.style.display = !q || li.dataset.search.includes(q) ? '' : 'none';
    }});
    document.querySelectorAll('section').forEach(sec => {{
      const any = [...sec.querySelectorAll('li.doc')].some(li => li.style.display !== 'none');
      sec.style.display = any ? '' : 'none';
    }});
  }});
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--community', default='epic', help='Zenodo community slug (default: epic)')
    ap.add_argument('--out', required=True, help='Output HTML file path')
    args = ap.parse_args()

    records = fetch_records(args.community)
    issues = curation_rows(records)
    page = build_page(records, args.community, issues)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(page)
    counts = {}
    for rec in records:
        if is_template(rec):
            continue
        counts[classify(rec)] = counts.get(classify(rec), 0) + 1
    summary = ', '.join(f'{dict(SECTIONS)[k]}: {v}' for k, v in
                        sorted(counts.items(), key=lambda kv: -kv[1]))
    print(f'{len(records)} records -> {args.out} ({summary}; '
          f'{len(issues)} curation issues)')


if __name__ == '__main__':
    sys.exit(main())
