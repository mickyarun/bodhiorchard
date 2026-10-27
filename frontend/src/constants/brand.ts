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

// Product identity shown in the UI. Read from here rather than hard-coding the
// name or logo paths in components, so a rebrand touches one file.

export const BRAND_NAME = 'Glideship'

export const BRAND_MARK = {
  light: '/assets/brand/glideship-mark.svg',
  dark: '/assets/brand/glideship-mark-dark.svg',
} as const
