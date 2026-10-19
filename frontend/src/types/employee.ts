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

/** Employee records — mirrors backend/app/schemas/employee.py. */

export type EmploymentType = 'full_time' | 'part_time' | 'contract' | 'intern'
export type EmployeeStatus = 'active' | 'on_notice' | 'exited'
export type Gender = 'female' | 'male' | 'non_binary' | 'prefer_not_to_say'
export type BloodGroup =
  | 'a_positive'
  | 'a_negative'
  | 'b_positive'
  | 'b_negative'
  | 'ab_positive'
  | 'ab_negative'
  | 'o_positive'
  | 'o_negative'

export interface EmployeeWork {
  employee_code: string | null
  designation: string | null
  department: string | null
  employment_type: EmploymentType
  status: EmployeeStatus
  date_of_joining: string | null
  date_of_exit: string | null
  country_code: string | null
  work_location: string | null
}

export interface EmployeeContact {
  phone: string | null
  personal_email: string | null
  emergency_contact_name: string | null
  emergency_contact_relation: string | null
  emergency_contact_phone: string | null
}

export interface EmployeePersonal extends EmployeeContact {
  date_of_birth: string | null
  gender: Gender | null
  blood_group: BloodGroup | null
}

export interface ManagerRef {
  user_id: string
  name: string
  is_primary: boolean
  is_active: boolean
}

export interface EmployeeRecord {
  user_id: string
  profile_id: string
  name: string
  email: string
  is_active: boolean
  work: EmployeeWork
  managers: ManagerRef[]
  /** Only present for HR, the owner and the employee themself. */
  personal: EmployeePersonal | null
  access: { edit_work: boolean; edit_personal: boolean; edit_managers: boolean }
  /** Set after a move to "exited": was the account deactivated too? */
  access_revoked: boolean | null
}

export interface DirectoryEntry {
  user_id: string
  name: string
  email: string
  is_active: boolean
  employee_code: string | null
  designation: string | null
  department: string | null
  status: EmployeeStatus
  primary_manager: ManagerRef | null
  manager_count: number
}

export interface MemberCandidate {
  user_id: string
  name: string
  email: string
}

export interface ManagerInput {
  user_id: string
  is_primary: boolean
}
