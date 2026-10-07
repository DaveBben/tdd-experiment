# A task image plus Node and Pi 1.0.4, for agent sessions. BASE is a task image pinned by digest.
ARG BASE
FROM node:24-bookworm-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 AS pi
RUN npm install -g --ignore-scripts @earendil-works/pi-coding-agent@1.0.4
FROM ${BASE}
COPY --from=pi /usr/local/bin/node /usr/local/bin/node
COPY --from=pi /usr/local/lib/node_modules/@earendil-works /usr/local/lib/node_modules/@earendil-works
RUN ln -s ../lib/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js /usr/local/bin/pi && pi --version
