# Peskinator Home Assistant Apps

Public Home Assistant App wrappers with automated stable-upstream updates.

| App | Upstream channel | Persistent data |
| --- | --- | --- |
| SFTPGo | Official stable GitHub releases | Home Assistant App configuration storage |
| Agregarr | Stable `bitr8/agregarr` Docker tags | Home Assistant App configuration storage |
| SongMirror | Upstream container digest | Home Assistant App data storage |
| LibraryDownloadarr | `ghcr.io/kikootwo/librarydownloadarr:latest` digest | Home Assistant App configuration storage |
| [SoulSync](soulsync/) | Official stable GitHub release + pinned GHCR digest | Private app state in `/data`; music in `/media`, inbox/downloads in `/share` |

The scheduled workflows only update wrapper code and version metadata. They do
not include or access App users, databases, certificates, host keys, uploads,
or Home Assistant credentials.
# GitHub-built Home Assistant images

The four wrapper apps LibraryDownloadarr, SFTPGo, SongMirror and SoulSync can
download versioned images from GitHub Container Registry instead of rebuilding
on the Home Assistant server. Runtime app storage stays on Home Assistant.

To perform the initial migration, run **Migrate apps to verified GitHub-built
images** once per app. It builds and pushes the next wrapper version, verifies
an anonymous registry pull, and only then commits the `image` and version fields
Home Assistant reads. Newly created GitHub container packages default to private;
set the `ha-<app>` package to public before retrying if verification reports that
anonymous pulls are unavailable. Never make the separate private-app images public.

Each existing daily upstream-sync workflow publishes and verifies its new image
before committing the Home Assistant update. An image build, push or visibility
failure therefore prevents advertising that update. Migration reruns detect an
already migrated app without inventing another wrapper version.

The initial migration versions are 0.1.1 (LibraryDownloadarr), 2.7.6-2 (SFTPGo),
0.1.26 (SongMirror), and 3.6.3-2 (SoulSync), assuming the current versions have
not advanced before migration. Other apps, including Agregarr, are unaffected.
