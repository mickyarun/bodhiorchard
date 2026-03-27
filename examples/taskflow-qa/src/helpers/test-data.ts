export const TEST_USER = {
  email: 'test@example.com',
  password: 'Test1234!',
  name: 'Test User',
}

export const ADMIN_USER = {
  email: 'admin@example.com',
  password: 'Admin1234!',
  name: 'Admin User',
}

let counter = 0

export function uniqueId(prefix = 'test'): string {
  counter += 1
  return `${prefix}-${Date.now()}-${counter}`
}

export function testTask(overrides: Partial<{ title: string; description: string }> = {}) {
  return {
    title: overrides.title || `Test Task ${uniqueId()}`,
    description: overrides.description || 'Created by QA automation',
  }
}
