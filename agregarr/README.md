# Agregarr Home Assistant Add-on

This add-on wraps the official `agregarr/agregarr` container and persists its configuration in Home Assistant storage.

## Exposed port

- `7171/tcp`: Agregarr web UI

## Persistence

Agregarr configuration is stored at `/app/config`, backed by the add-on data directory.

## Optional media mounts

The add-on also mounts:

- `/media`
- `/share`

You can use these from Agregarr when configuring placeholder/root folders for movies and TV content.

## Updating

To move to a newer upstream Agregarr release:

This add-on currently tracks the upstream `latest` image because Agregarr does not appear to publish stable version-tagged images that Home Assistant can consume directly.
