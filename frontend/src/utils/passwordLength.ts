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

/**
 * The length a new password must have. Mirrors the backend's
 * ``ChangePasswordRequest.new_password`` (min_length=8, max_length=128),
 * so the form says what's wrong before the API refuses it.
 */

export const PASSWORD_MIN_LENGTH = 8
export const PASSWORD_MAX_LENGTH = 128

/** A Vuetify rule: ``true`` when the length is allowed, else what to fix. */
export function passwordLengthRule(value: string): true | string {
  if (value.length < PASSWORD_MIN_LENGTH) return `At least ${PASSWORD_MIN_LENGTH} characters`
  if (value.length > PASSWORD_MAX_LENGTH) return `At most ${PASSWORD_MAX_LENGTH} characters`
  return true
}
