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

/** Who's out on a given day, for the team calendar. */
import type { CalendarEntry, HolidayRead } from '@/types/leave'
import { isWithin, weekdayIndex } from '@/utils/leaveDates'

export interface DayContext {
  /** The caller's policy holidays, shown as day labels. */
  holidays: HolidayRead[]
}

export function holidayOn(iso: string, holidays: HolidayRead[]): HolidayRead | null {
  return holidays.find(h => h.date === iso) ?? null
}

/** Entries covering `iso`, each skipped on its owner's weekly days off (a
 *  week of leave doesn't paint the weekend). The owner's working days, not
 *  the viewer's: a colleague on another policy may work when you don't.
 *  Leave first, then WFH; by name within each. */
export function entriesOnDay(entries: CalendarEntry[], iso: string): CalendarEntry[] {
  const weekday = weekdayIndex(iso)
  return entries
    .filter(e => e.working_days.includes(weekday) && isWithin(iso, e.start_date, e.end_date))
    .sort((a, b) => {
      const kindOrder = Number(a.kind === 'wfh') - Number(b.kind === 'wfh')
      return kindOrder || a.user.name.localeCompare(b.user.name)
    })
}
