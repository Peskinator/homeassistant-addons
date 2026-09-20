ARG BUILD_SONGMIRROR_IMAGE="ghcr.io/ahnafnafee/songmirror@sha256:f6cd1fc25ec52a2eb592b8ba7186fca8a63a845de27105a502e6261e1a4a63dd"
FROM ${BUILD_SONGMIRROR_IMAGE}

ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION="Self-hosted playlist sync with scheduled, persistent metadata archives."
ARG BUILD_NAME="SongMirror"
ARG BUILD_REF
ARG BUILD_REPOSITORY
ARG BUILD_VERSION

LABEL \
  io.hass.name="${BUILD_NAME}" \
  io.hass.description="${BUILD_DESCRIPTION}" \
  io.hass.arch="${BUILD_ARCH}" \
  io.hass.type="addon" \
  io.hass.version="${BUILD_VERSION}" \
  org.opencontainers.image.title="${BUILD_NAME}" \
  org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
  org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
  org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/tree/main/songmirror" \
  org.opencontainers.image.created="${BUILD_DATE}" \
  org.opencontainers.image.revision="${BUILD_REF}" \
  org.opencontainers.image.version="${BUILD_VERSION}"

ENV SONGMIRROR_DATA_DIR=/data \
    SONGMIRROR_ENV_FILE=/data/app.env \
    SPOTIFY_TOKEN_CACHE=/data/spotify_token_cache \
    SPOTIFY_TRACKS_CACHE=/data/spotify_tracks_cache.json \
    SPOTIFY_CACHE_FILE=/data/spotify_resolve_cache.json \
    SONG_CACHE_FILE=/data/song_cache.db \
    DOWNLOAD_STATE_FILE=/data/download_state.json

COPY run.sh dual_stack.py /
RUN chmod 0755 /run.sh

EXPOSE 8080

# Serve both address families without running the scheduler twice.
CMD ["/run.sh"]
