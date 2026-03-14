ARG BUILD_SFTPGO_VERSION="v2.7.0"

FROM drakkan/sftpgo:${BUILD_SFTPGO_VERSION}

ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION="Self-hosted SFTP server with a web admin UI, backed by persistent Home Assistant storage."
ARG BUILD_NAME="SFTPGo"
ARG BUILD_REF
ARG BUILD_REPOSITORY
ARG BUILD_VERSION

USER root

COPY run.sh /run.sh

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && chmod 0755 /run.sh

ENTRYPOINT ["/run.sh"]

LABEL \
    io.hass.name="${BUILD_NAME}" \
    io.hass.description="${BUILD_DESCRIPTION}" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version="${BUILD_VERSION}" \
    org.opencontainers.image.title="${BUILD_NAME}" \
    org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/tree/main/sftpgo" \
    org.opencontainers.image.created="${BUILD_DATE}" \
    org.opencontainers.image.revision="${BUILD_REF}" \
    org.opencontainers.image.version="${BUILD_VERSION}"
