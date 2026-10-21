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

/** A mailto: link that opens the sender's own mail app with someone's sign-in details filled in. */
export interface Credentials {
  name: string
  email: string
  password: string
  loginUrl: string
}

export function credentialsMailto({ name, email, password, loginUrl }: Credentials): string {
  const subject = encodeURIComponent('Your login credentials')
  const body = encodeURIComponent(
    `Hi ${name},\n\n` +
      `Your login credentials:\n` +
      `Email: ${email}\n` +
      `Temporary Password: ${password}\n\n` +
      `Log in here: ${loginUrl}\n` +
      `You will be asked to change your password on first login.`,
  )
  return `mailto:${email}?subject=${subject}&body=${body}`
}
