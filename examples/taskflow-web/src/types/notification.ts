export type NotificationType =
  | 'task_assigned'
  | 'task_comment'
  | 'task_status_changed'
  | 'invoice_ready'
  | 'reminder'

export interface Notification {
  id: number
  type: NotificationType
  title: string
  body: string
  time: string
  isRead: boolean
  isDismissed: boolean
}
