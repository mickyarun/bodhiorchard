# TaskFlow Web

Vue 3 frontend for TaskFlow — task board, notifications, and billing dashboard.

## Setup

```bash
cd examples/taskflow-web
npm install
```

## Run

```bash
npm run dev -- --port 9002
```

App: http://localhost:9002

Expects the API running at `http://localhost:9001` (configured in `src/services/api.ts`).

## Views

- `/login`, `/register` — Authentication forms
- `/tasks` — Kanban board with drag-and-drop columns
- `/tasks/:id` — Task detail with comments
- `/billing` — Plans, usage meter, invoice history

## Components

- `NotificationBell` — Header bell icon with unread badge + dropdown panel
- `NotificationPreferences` — Email/push/digest settings form
