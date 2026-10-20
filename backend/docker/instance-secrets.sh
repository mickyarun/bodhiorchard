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
# start and keeps them on volumes, where they survive rebuilds. The bridge
# secret sits on a volume of its own (BRIDGE_SECRET_DIR): the multiplayer
# container mounts only that one, so it never sees the backend's keys. A value set in the
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
    status=0
    python -m scripts.rotate_encryption_key --rotate || status=$?
    if [ "$status" -eq 1 ]; then
        echo "Some stored secrets couldn't be re-encrypted (listed above);" \
            "starting anyway. Re-save them in Settings." >&2
    elif [ "$status" -ne 0 ]; then
        echo "Re-encrypting stored secrets failed (exit $status, see above);" \
            "starting anyway and trying again on the next start." >&2
    fi
}

if [ -n "${INSTANCE_SECRETS_DIR:-}" ]; then
    BRIDGE_SECRET_DIR="${BRIDGE_SECRET_DIR:-$INSTANCE_SECRETS_DIR}"

    # instance_secret DIR NAME [UMASK]: print the secret NAME in DIR, creating it once.
    instance_secret() {
        file="$1/$2"
        if [ ! -s "$file" ]; then
            echo "==> Generating $2 for this install" >&2
            # Write then rename, so a reader never sees half a file.
            if ! (umask "${3:-077}" && mkdir -p "$1" && \
                python -c "import secrets; print(secrets.token_urlsafe(48))" > "$file.tmp" && \
                mv "$file.tmp" "$file"); then
                echo "Can't write $file. Mount a writable volume at $1" \
                    "(see docker-compose.yml) or set the value in the environment." >&2
                exit 1
            fi
        fi
        cat "$file"
    }

    if [ -z "${SECRET_KEY:-}" ] || [ "$SECRET_KEY" = "change-me-in-production" ]; then
        SECRET_KEY="$(instance_secret "$INSTANCE_SECRETS_DIR" secret_key)"
        export SECRET_KEY
    fi
    if [ -z "${COLYSEUS_BRIDGE_SECRET:-}" ] || \
        [ "$COLYSEUS_BRIDGE_SECRET" = "dev-colyseus-bridge-secret" ]; then
        # Readable by the multiplayer container's own (non-root) user.
        COLYSEUS_BRIDGE_SECRET="$(instance_secret "$BRIDGE_SECRET_DIR" colyseus_bridge_secret 022)"
        export COLYSEUS_BRIDGE_SECRET
    fi
    if [ -z "${ENCRYPTION_KEY:-}" ] || [ "$ENCRYPTION_KEY" = "$LEGACY_ENCRYPTION_KEY" ]; then
        ENCRYPTION_KEY="$(instance_secret "$INSTANCE_SECRETS_DIR" encryption_key)"
        export ENCRYPTION_KEY
    fi
    case ",${ENCRYPTION_KEY_PREVIOUS:-}," in
        *",$LEGACY_ENCRYPTION_KEY,"*) ;;
        *) ENCRYPTION_KEY_PREVIOUS="${ENCRYPTION_KEY_PREVIOUS:+$ENCRYPTION_KEY_PREVIOUS,}$LEGACY_ENCRYPTION_KEY" ;;
    esac
    export ENCRYPTION_KEY_PREVIOUS
fi
