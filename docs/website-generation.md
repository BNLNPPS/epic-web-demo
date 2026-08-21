# Generating the ePIC website from collaboration data

The ePIC collaboration website, www.epic-eic.org, is a static GitHub
Pages site built from the public repository `eic/www.epic-eic.org`. Its
prose pages (science, detector, collaboration governance) are maintained
adequately by hand. Its list pages — documents, papers, talks, figures,
meetings — are either hand-maintained and therefore stale, or empty
placeholders. Nearly all of them can be generated from data the
collaboration already keeps in Zenodo, InspireHEP, and Indico, so that
the pages are always current and require no manual upkeep.

The documents demonstrator in this repository
(`documents/zenodo_documents.py`, served at
https://epic-devcloud.org/demo/documents/) establishes the pattern: a
standard-library Python script fetches the ePIC community on Zenodo,
classifies the records, renders a single self-contained page, and
appends a Curation section listing the metadata and registration issues
found along the way.

## Site audit, 2026-08-21

All 57 pages of the site were fetched and assessed. Findings:

- The Documents category pages `papers.html` and `tech.html` are "TBD"
  placeholders; `figures.html` contains three "Instructions come here"
  stubs; there is no theses page. `analysis_notes.html` and
  `reports.html` are hand-maintained lists whose Zenodo links include
  five outdated version DOIs (the current versions are in the
  community).
- A keyword system is defined and documented on
  `documents/keywords.html`, including document keywords (`ana_note`,
  `tech_note`) and per-conference keywords (`dis2024`, `chep2024`, …).
  About 100 presentations in the Zenodo community already carry
  conference keywords, but no page is generated from them:
  `public/conference_talks.html` contains only committee contact
  information, while `meetings/conferences.html` is a hand-maintained
  85-link conference index.
- Several further pages are empty or near-empty placeholders:
  `meetings/reviews.html`, `sc/projects.html`, `sc/decision.html`,
  `sc/evdisp.html`, `collaboration/outreach.html`.
- Of the 172 records in the Zenodo community, 25 fall into no document
  category for lack of keywords, six technical notes lack `tech_note`,
  and several notes carry a resource type inconsistent with their
  content. The Curation section of the demonstrator enumerates these.

## Generation opportunities

| Page | Present state | Source | Generated product |
|---|---|---|---|
| `documents/analysis_notes`, `documents/reports` | hand-maintained, stale links | Zenodo community | note lists (demonstrated) |
| `documents/papers`, `documents/tech` | placeholders | Zenodo; InspireHEP collaboration search | publication and technical note lists |
| theses | no page | InspireHEP thesis records; Zenodo Thesis type | thesis list |
| `public/conference_talks` | contacts only | Zenodo conference keywords × conference index | talks by conference |
| `documents/figures`, `documents/photos` | placeholders / portal text | Zenodo image, plot, diagram, photo records | galleries with thumbnails |
| `collaboration/coming`, `meetings/reviews` | hand-maintained / placeholder | Indico (BNL category 402, public export) | upcoming meetings and reviews |
| `public/institutions` | hand-maintained | ePIC phonebook | institution list; contingent on an export interface (the phonebook is behind authentication) |
| site-wide | — | curation checks | maintainer report: empty pages, dead and outdated links, keyword gaps |

## Nightly maintenance

A nightly cron job provides the pages and their quality control:

1. **Generation.** Run the generator scripts against their sources and
   publish the regenerated pages.
2. **Curation checks.** Programmatic checks of the kind implemented in
   `zenodo_documents.py`: missing canonical keywords, unexpected
   resource types, template records, duplicate titles, and a cross-check
   of the hand-maintained site pages against the Zenodo community
   (unregistered records, outdated version links), extended with
   site-wide link and placeholder checks.
3. **AI assessment.** An LLM pass over the curation output and the diff
   since the previous run, producing a short maintainer report:
   proposed categories for unclassified records, drafted keyword and
   metadata fixes for a curator to apply, and notable changes in the
   document corpus. The report is published alongside the generated
   pages.

The programmatic steps are deterministic and cheap; the AI step reads
their output rather than the raw sources, so its cost is small and its
claims are grounded in the checked data.

## Adoption path

The generators are self-contained and portable. On adoption by the
collaboration they move into `eic/www.epic-eic.org` as a `scripts/`
directory with a scheduled GitHub Actions workflow that regenerates the
pages and commits them — GitHub Pages serves only static content, but a
scheduled Action satisfies the update requirement. Until then this
repository serves the demonstrators at https://epic-devcloud.org/demo/.
