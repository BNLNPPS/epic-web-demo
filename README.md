# epic-web-demo

Demonstrators served at `https://epic-devcloud.org/demo/`.

The `/demo/` area holds self-contained demonstrator pages that are
independent of the production applications on this host (`/prod`,
swf-remote; `/doc`, corun-ai). It requires no Apache configuration:
`epic-devcloud.org/` serves the static document root
`/var/www/epic-devcloud-landing`, and `/demo/` is a subdirectory of it.

## Layout

- `site/` — static files for the demo area itself (`/demo/` index page).
- `documents/` — ePIC document list demonstrator: `zenodo_documents.py`
  generates a categorized document list page from the
  [ePIC community on Zenodo](https://zenodo.org/communities/epic)
  (public REST API, standard library only). Served at
  `/demo/documents/`. A Curation section flags Zenodo metadata gaps,
  duplicate titles, and — by cross-checking the epic-eic.org document
  pages — notes missing from the community and outdated version links. The same script run offline can generate document
  pages for the epic-eic.org github-pages site.
- `deploy/update_from_dev.sh` — copies `site/` into the served tree and
  runs each demonstrator's generator. Run after any change here; the
  live pages do not update otherwise.
- `scripts/nightly_maintenance.sh` — the nightly cron job (admin
  crontab, 03:15 UTC): regenerates the demonstrator pages, extracts
  their curation output, and publishes an AI assessment report at
  `/demo/documents/maintenance.html`. State in `~/.epic-web-demo/`;
  log in `/tmp/cron_epic_web_demo.log`.

## Docs

- `docs/website-generation.md` — audit of www.epic-eic.org, the
  generation opportunities across the site, and the nightly maintenance
  design (generation, curation checks, AI assessment report).

## Adding a demonstrator

Create a subdirectory with its generator or static content, add its
output step to `deploy/update_from_dev.sh`, and link it from
`site/index.html`.
