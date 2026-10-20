#!/bin/sh
# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#
# Multiplayer container start. The bridge secret is shared with the
# backend: when it isn't set in the environment, read the one the backend
# generated on the shared secrets volume (backend/docker/instance-secrets.sh),
# waiting briefly in case the backend is still starting.

set -e

# The old dev default counts as unset, as it does on the backend side, or
# the two would disagree and every bridge call would be refused.
if [ -n "${INSTANCE_SECRETS_DIR:-}" ] && { [ -z "${COLYSEUS_BRIDGE_SECRET:-}" ] || \
    [ "$COLYSEUS_BRIDGE_SECRET" = "dev-colyseus-bridge-secret" ]; }; then
    file="$INSTANCE_SECRETS_DIR/colyseus_bridge_secret"
    waited=0
    while [ ! -s "$file" ] && [ "$waited" -lt "${BRIDGE_SECRET_WAIT_SECONDS:-60}" ]; do
        sleep 1
        waited=$((waited + 1))
    done
    if [ ! -s "$file" ]; then
        echo "COLYSEUS_BRIDGE_SECRET isn't set and $file never appeared." \
            "Start the backend with the secrets_data volume, or set the secret." >&2
        exit 1
    fi
    COLYSEUS_BRIDGE_SECRET="$(cat "$file")"
    export COLYSEUS_BRIDGE_SECRET
fi

exec node dist/multiplayer/src/main.js
