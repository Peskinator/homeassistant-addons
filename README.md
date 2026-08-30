# Peskinator Home Assistant Apps

Public Home Assistant App wrappers with automated stable-upstream updates.

| App | Upstream channel | Persistent data |
| --- | --- | --- |
| SFTPGo | Official stable GitHub releases | Home Assistant App configuration storage |
| Agregarr | Stable `bitr8/agregarr` Docker tags | Home Assistant App configuration storage |
| LibraryDownloadarr | `ghcr.io/kikootwo/librarydownloadarr:latest` digest | Home Assistant App configuration storage |

The scheduled workflows only update wrapper code and version metadata. They do
not include or access App users, databases, certificates, host keys, uploads,
or Home Assistant credentials.
