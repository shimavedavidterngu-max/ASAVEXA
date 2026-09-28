# ASAVEXA frontend — static file image.
#
# NOT built in the sandbox that produced this codebase (same blocked
# network path as the API's Dockerfile — see docs/runtime-verification.md).
#
# Found during the Phase 7 deployment audit: docker-compose.yml
# previously bind-mounted the ENTIRE frontend/ directory as nginx's
# webroot, which meant nginx.conf itself and frontend/tests/ were
# servable to any client (curl http://localhost:8080/nginx.conf would
# have returned the internal proxy configuration verbatim). This
# Dockerfile fixes that structurally: only index.html and src/ are
# copied into the image. There is no volume mount in production, so
# there is nothing else in the image root to accidentally serve — not
# a config rule that could be forgotten or misconfigured, but simply
# not present.
FROM nginx:alpine

COPY index.html /usr/share/nginx/html/index.html
COPY src/ /usr/share/nginx/html/src/
COPY nginx.conf /etc/nginx/conf.d/default.conf
