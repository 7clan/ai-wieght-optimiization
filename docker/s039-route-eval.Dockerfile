# Session 039B trusted route/invariant evaluation image (BUILD RECIPE ONLY).
#
# Build ONLY inside an approved image workflow (see
# .github/workflows/s039-docker-eval.yml or an equivalent user-approved
# environment). Building downloads Prisma engines at build time so that
# evaluation containers never need network access. After building, PUSH the
# image to a registry (the workflow pushes to GHCR) and record its registry
# manifest digest with:
#   docker image inspect --format '{{index .RepoDigests 0}}' <image>:ci
# (only populated after the push). Pass that exact image@sha256:<digest> to
# the evaluators. Do NOT use '{{.Id}}': that is the local config digest with
# no repository name — the evaluators reject bare sha256 IDs, floating tags,
# and they never pull (--pull never), so the digest-pinned image must also be
# present on (pulled by) every runner that executes it.
#
# Base pinned to the linux/amd64 manifest digest of node:24 recorded on
# 2026-11-10 (NODE_VERSION=24.22.2, config created 2026-11-05). Re-verify
# before any rebuild.
FROM node:24@sha256:6b9d4ea31e614e29f364bf75758458731eb1e105b80c99667438dd6b3fe262e0

# Prisma 6.19.3 was the version smoke-validated against the trusted
# controls in Session 039B (host tier). Keep it pinned.
RUN npm install -g prisma@6.19.3 @prisma/client@6.19.3 \
    && npm cache clean --force

ENV PRISMA_HIDE_UPDATE_MESSAGE=1 \
    PRISMA_SKIP_POSTINSTALL_GENERATE=1

# Smoke marker for humans inspecting the image; not used by the harness.
LABEL org.opencontainers.image.title="s039-route-eval" \
      org.opencontainers.image.description="Node 24 + Prisma 6.19.3 trusted evaluation image for Session-039 Docker-only candidate execution" \
      org.opencontainers.image.source="https://github.com/7clan/ai-wieght-optimiization"
