ARG BUILD_LIBRARYDOWNLOADARR_IMAGE="ghcr.io/kikootwo/librarydownloadarr@sha256:c3c36e73879bcd49be6e7b8e761d60ca27d85d6773732e3786bb438526318ccc"
FROM ${BUILD_LIBRARYDOWNLOADARR_IMAGE}

ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION="A self-hosted web interface to browse and download media from Plex libraries."
ARG BUILD_NAME="LibraryDownloadarr"
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
    org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/tree/main/librarydownloadarr" \
    org.opencontainers.image.created="${BUILD_DATE}" \
    org.opencontainers.image.revision="${BUILD_REF}" \
    org.opencontainers.image.version="${BUILD_VERSION}"
