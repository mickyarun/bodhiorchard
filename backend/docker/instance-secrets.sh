# shellcheck shell=sh
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
# Per-install secrets for Full Docker, sourced by entrypoint.sh.
#
# Full Docker ships without SECRET_KEY, ENCRYPTION_KEY or
# COLYSEUS_BRIDGE_SECRET. Fixed values would let anyone with the source
# forge sign-ins, read stored integration tokens from a database dump, or
# call the multiplayer bridge. So each install generates its own on first
# start and keeps them on the secrets volume, where they survive rebuilds
# and the multiplayer container reads the shared one. A value set in the
# environment always wins. app/instance_secrets.py reads the same files
# for processes started outside this entrypoint.
#
# Opt-in: only docker-compose.yml sets INSTANCE_SECRETS_DIR. Production and
# Hybrid don't, so their own checks stay in charge (the backend refuses a
# missing or default key when ENV=production).
#
# Tokens stored under the old shared default ENCRYPTION_KEY (installs from
# before, or a token saved in Hybrid on the same database) stay readable
# and are re-encrypted under this install's key on every start.

LEGACY_ENCRYPTION_KEY="change-me-encryption-key"

# Run after migrations; a no-op outside Full Docker. Never stops the start.
rotate_from_default_key() {
    [ -n "${INSTANCE_SECRETS_DIR:-}" ] || return 0
    echo "==> Re-encrypting stored secrets still under the old default key"
    if ! python -m scripts.rotate_encryption_key --rotate; then
        echo "Some stored secrets couldn't be re-encrypted (listed above);" \
            "starting anyway. Re-save them in Settings." >&2
    fi
}

if [ -n "${INSTANCE_SECRETS_DIR:-}" ]; then
    # instance_secret NAME: print this install's secret NAME, creating it once.
    instance_secret() {
        file="$INSTANCE_SECRETS_DIR/$1"
        if [ ! -s "$file" ]; then
            echo "==> Generating $1 for this install" >&2
            # Write then rename, so a reader never sees half a file.
            if ! (umask 077 && mkdir -p "$INSTANCE_SECRETS_DIR" && \
                python -c "import secrets; print(secrets.token_urlsafe(48))" > "$file.tmp" && \
                mv "$file.tmp" "$file"); then
                echo "Can't write $file. Mount a writable volume at $INSTANCE_SECRETS_DIR" \
                    "(see docker-compose.yml) or set the value in the environment." >&2
                exit 1
            fi
        fi
        cat "$file"
    }

    if [ -z "${SECRET_KEY:-}" ] || [ "$SECRET_KEY" = "change-me-in-production" ]; then
        SECRET_KEY="$(instance_secret secret_key)"
        export SECRET_KEY
    fi
    if [ -z "${COLYSEUS_BRIDGE_SECRET:-}" ] || \
        [ "$COLYSEUS_BRIDGE_SECRET" = "dev-colyseus-bridge-secret" ]; then
        COLYSEUS_BRIDGE_SECRET="$(instance_secret colyseus_bridge_secret)"
        export COLYSEUS_BRIDGE_SECRET
    fi
    if [ -z "${ENCRYPTION_KEY:-}" ] || [ "$ENCRYPTION_KEY" = "$LEGACY_ENCRYPTION_KEY" ]; then
        ENCRYPTION_KEY="$(instance_secret encryption_key)"
        export ENCRYPTION_KEY
    fi
    case ",${ENCRYPTION_KEY_PREVIOUS:-}," in
        *",$LEGACY_ENCRYPTION_KEY,"*) ;;
        *) ENCRYPTION_KEY_PREVIOUS="${ENCRYPTION_KEY_PREVIOUS:+$ENCRYPTION_KEY_PREVIOUS,}$LEGACY_ENCRYPTION_KEY" ;;
    esac
    export ENCRYPTION_KEY_PREVIOUS
fi
