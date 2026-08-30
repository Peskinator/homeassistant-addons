# Agregarr Home Assistant Add-on

This add-on wraps the `bitr8/agregarr:develop` container from the maintained recommender fork and persists its configuration in Home Assistant storage.

## Exposed port

- `7171/tcp`: Agregarr web UI

## Persistence

Agregarr configuration is stored at `/app/config`, backed by the add-on data directory.

## Optional media mounts

The add-on also mounts:

- `/media`
- `/share`

You can use these from Agregarr when configuring placeholder/root folders for movies and TV content.

## Upstream image

This add-on currently tracks `bitr8/agregarr:develop`, matching the maintained fork's recommended Docker image.

Existing configuration from the original `agregarr/agregarr:latest` image is compatible because the persisted `/app/config` path is unchanged.
