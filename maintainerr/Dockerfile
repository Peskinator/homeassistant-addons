# Use the official Maintainerr image as the base
FROM ghcr.io/maintainerr/maintainerr:latest

# Home Assistant add-ons normally run as root.
# We switch to root so we can modify /opt/data and write to /data.
USER root

# Make Maintainerr's data directory point at Home Assistant's
# persistent volume for this add-on (/data).
# /data is automatically persisted by the Supervisor.
RUN rm -rf /opt/data && ln -s /data /opt/data

# Keep running as root inside Home Assistant.
# Maintainerr will still see /opt/data as its data directory,
# but everything will be stored under the add-on's /data volume,
# which survives reboots.
USER root
