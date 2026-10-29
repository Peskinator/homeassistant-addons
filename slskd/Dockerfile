ARG BUILD_SLSKD_VERSION="0.26.2"
ARG BUILD_SLSKD_IMAGE="ghcr.io/slskd/slskd@sha256:d0963a3e5b16facd295bf4f2156dad0182f246b1b21a032cae12f5494c694843"
FROM ${BUILD_SLSKD_IMAGE}
ARG BUILD_ARCH
ARG BUILD_VERSION
ARG BUILD_REF
LABEL io.hass.name="slskd" \
      io.hass.type="addon" \
      io.hass.arch="${BUILD_ARCH}" \
      io.hass.version="${BUILD_VERSION}" \
      org.opencontainers.image.source="https://github.com/Peskinator/homeassistant-addons" \
      org.opencontainers.image.revision="${BUILD_REF}"
COPY run.sh /ha-run.sh
RUN chmod 755 /ha-run.sh
ENTRYPOINT ["/bin/bash", "/ha-run.sh"]
CMD ["./slskd"]
