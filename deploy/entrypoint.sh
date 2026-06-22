#!/bin/sh
# NEOS runtime container entrypoint (S0.1).
#
# Secret injection model (designed in NOW so S0.2 is a config swap, not a rebuild):
#   1. Docker secrets / AWS-Secrets-Manager-mounted files at /run/secrets/<NAME> are
#      loaded into the environment (env already set wins — explicit override).
#   2. Plain env injection (compose `environment:`) also works, unchanged.
# Either source feeds the same boot self-check; NOTHING is baked into the image.
set -eu

if [ -d /run/secrets ]; then
  for f in /run/secrets/*; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    eval "cur=\${$name:-}"
    if [ -z "$cur" ]; then
      export "$name=$(cat "$f")"
    fi
  done
fi

# Credential-gated boot: refuse (non-zero) if required config absent — never silent no-op.
python -m runtime.selfcheck

exec "$@"
