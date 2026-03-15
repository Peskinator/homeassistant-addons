ARG BUILD_UPSTREAM="3.1.0"

FROM ghcr.io/maintainerr/maintainerr:${BUILD_UPSTREAM}

USER root

COPY run.sh /run.sh

RUN apk add --no-cache su-exec \
    && chmod 0755 /run.sh

ENTRYPOINT ["/run.sh"]
