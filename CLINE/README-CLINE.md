# CLINE — working copy

This folder is the **only** place where Cline makes changes. The project root and
`../RAW data/` are left untouched.

- Contents: full copy of the VALÉ — Obsidian No. 01 starting files, plus `node_modules/`
  so this copy runs standalone.
- Original snapshot: `../RAW data/` (never edit it).

## Run it

```bash
cd CLINE
npm run dev      # dev server
npm run build    # production build
npm run preview  # preview the build
```

Note: if this folder is ever re-synced from the project root with `rsync --delete`,
add `--exclude 'README-CLINE.md'` so this note survives.
