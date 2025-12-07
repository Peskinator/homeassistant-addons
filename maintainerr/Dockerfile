FROM ghcr.io/maintainerr/maintainerr:latest

# Our wrapper script that prepares /data and then starts Maintainerr
COPY --chmod=755 run.sh /run.sh

# Run wrapper as root so it can fix ownership on /data
USER root

ENTRYPOINT ["/run.sh"]
