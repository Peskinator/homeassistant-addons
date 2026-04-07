ARG BUILD_FROM=python:3.12-slim
FROM ${BUILD_FROM}

ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION="Shared dog custody tracker with a mobile-friendly calendar UI."
ARG BUILD_NAME="Dog Custody Tracker"
ARG BUILD_REF
ARG BUILD_REPOSITORY
ARG BUILD_VERSION

WORKDIR /app
COPY . /app

ENV DOG_WALK_HOST=0.0.0.0
ENV DOG_WALK_PORT=8420
ENV DOG_WALK_DATA_DIR=/data

EXPOSE 8420

CMD ["python3", "app.py"]

LABEL \
    io.hass.name="${BUILD_NAME}" \
    io.hass.description="${BUILD_DESCRIPTION}" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version="${BUILD_VERSION}" \
    org.opencontainers.image.title="${BUILD_NAME}" \
    org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/tree/main/dog_custody_tracker" \
    org.opencontainers.image.created="${BUILD_DATE}" \
    org.opencontainers.image.revision="${BUILD_REF}" \
    org.opencontainers.image.version="${BUILD_VERSION}"
