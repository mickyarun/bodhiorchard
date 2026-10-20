// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/** Saving a downloaded file (a CSV export, a document) from a Blob. */

/**
 * The file name a `Content-Disposition` header asks for, or `fallback`.
 * The encoded `filename*` wins over the plain `filename` (RFC 6266); only
 * the encoded form is percent-decoded, so a plain name may contain `%`.
 */
export function filenameFrom(disposition: string | undefined, fallback: string): string {
  const header = disposition ?? ''
  const encoded = /filename\*=UTF-8''([^;\s]+)/i.exec(header)
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1])
    } catch {
      // Malformed encoding: fall through to the plain name.
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header)
  return plain ? plain[1] : fallback
}

/** Save `blob` as `filename` via a temporary link. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  // Let the browser start the download before releasing the copy.
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
