# Dog Custody Tracker

Self-hosted shared dog custody tracker for Home Assistant.

## Features

- Mobile-friendly month calendar
- Running totals for Frank and Kurt
- Future planning by date range
- Direct import from a public Google Sheet URL
- Manual day-by-day edits
- SQLite-backed storage inside the add-on `/data` directory

## Notes

- This repository stores the code only, not personal walk history.
- Releases are published as prebuilt multi-arch container images on GHCR for Home Assistant to pull directly.
- After installing the add-on, import your existing history from the app UI using the public Google Sheet URL.
- If you already have a trusted SQLite database from local testing, you can upload it once from the app UI.
- The app listens on port `8420`.

## Suggested workflow

1. Install the add-on from this repository.
2. Start the add-on.
3. Open the web UI.
4. Import the current Google Sheet history.
5. Later, add Home Assistant automations for notifications.
