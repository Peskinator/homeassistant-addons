ARG BUILD_SOULSYNC_VERSION="3.6.1"
ARG BUILD_SOULSYNC_IMAGE="ghcr.io/nezreka/soulsync@sha256:095926b17597dbf132ef16cb865bf850e255e218bc6ee9439cdbde2f8acadc0e"
FROM ${BUILD_SOULSYNC_IMAGE} AS upstream
RUN /opt/venv/bin/python -c 'import json,os; json.dump({k:v for k,v in os.environ.items() if k not in {"HOSTNAME","PWD","SHLVL","_"}}, open("/ha-upstream-env.json","w"))'

# Do not inherit upstream's VOLUME declarations. Anonymous /app/* volumes
# would silently become empty on Supervisor rebuild/upgrade. Copy the
# upstream root filesystem into a clean image, then link all mutable paths
# to HA's explicit /data, /media and /share mounts before upstream starts.
FROM scratch
COPY --from=upstream / /
ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_REF
ARG BUILD_REPOSITORY="Peskinator/homeassistant-addons"
ARG BUILD_VERSION
ARG BUILD_SOULSYNC_VERSION="3.6.1"
LABEL io.hass.name="SoulSync" \
      io.hass.description="Music requests, discovery, downloads and library management." \
      io.hass.arch="${BUILD_ARCH}" \
      io.hass.type="addon" \
      io.hass.version="${BUILD_VERSION}" \
      org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
      org.opencontainers.image.version="${BUILD_VERSION}" \
      org.opencontainers.image.revision="${BUILD_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      io.peskinator.upstream.version="${BUILD_SOULSYNC_VERSION}"
ENV PATH="/opt/venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin" \
    LANG=C.UTF-8 \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    SOULSYNC_IN_DOCKER=1 \
    SOULSYNC_CONFIG_PATH=/app/config/config.json \
    DATABASE_PATH=/app/data/music_library.db \
    VIDEO_DATABASE_PATH=/app/data/video_library.db \
    AUDIOBOOK_DATABASE_PATH=/app/data/audiobooks.db \
    HOME=/data/home \
    XDG_CACHE_HOME=/data/cache
WORKDIR /app
COPY bootstrap.py /ha-bootstrap.py
EXPOSE 8008 8888 8889
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8008/ >/dev/null || exit 1
ENTRYPOINT ["/opt/venv/bin/python", "/ha-bootstrap.py"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:application"]
