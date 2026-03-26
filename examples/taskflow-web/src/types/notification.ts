export interface Notification {
  id: number
  type: 'task_assigned' | 'task_comment' | 'task_status_changed' | 'invoice_ready' | 'reminder'
  title: string
  body: string | null
  link: string | null
  is_read: boolean
  created_at: string | null  // ISO 8601
}
