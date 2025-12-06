# Wrapper image for Maintainerr as a Home Assistant add-on.
# Use the upstream Maintainerr image as the base.
ARG BUILD_FROM=ghcr.io/maintainerr/maintainerr:latest
FROM ${BUILD_FROM}

# Make sure we can modify /opt/data
USER root

# Replace /opt/data with a symlink to the add-on's persistent /data
# (Home Assistant mounts a persistent directory at /data for every add-on.)
RUN rm -rf /opt/data && ln -s /data /opt/data

# Switch back to the default user Maintainerr expects
# (it normally runs as uid 1000 inside the container)
USER 1000
