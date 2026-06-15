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

// Shared types for the Company Quiz Game. Field names match the backend's
// camelCase serialization aliases.

export type QuizQuestionType = 'multiple_choice' | 'scramble' | 'fill_blank'
export type QuizDifficulty = 'easy' | 'medium' | 'hard' | 'mixed'
export type QuizQuestionStatus = 'draft' | 'approved' | 'rejected' | 'used'

/** A submitted answer's type-shaped payload: {index} for MCQ, {text} otherwise. */
export interface QuizResponse {
  index?: number
  text?: string
}

export interface QuizQuestionPublic {
  id: string
  questionType: QuizQuestionType
  difficulty: QuizDifficulty
  prompt: string
  payload: Record<string, unknown>
  category: string | null
}

export interface QuizActive {
  id: string
  quizDate: string
  openAt: string
  revealAt: string
  alreadyAnswered: boolean
  question: QuizQuestionPublic
}

export interface QuizAnswerResult {
  accepted: boolean
  alreadyAnswered: boolean
}

export interface QuizUserAnswer {
  response: QuizResponse
  isCorrect: boolean
  points: number
}

export interface QuizReveal {
  id: string
  questionType: QuizQuestionType
  prompt: string
  payload: Record<string, unknown>
  answerKey: Record<string, unknown>
  explanation: string
  category: string | null
  sourceRefs: Record<string, unknown>
  totalAnswers: number
  correctAnswers: number
  percentCorrect: number
  yourAnswer: QuizUserAnswer | null
}

export interface QuizLeaderboardEntry {
  userId: string
  userName: string
  totalPoints: number
  correctCount: number
}

export interface QuizReviewItem {
  id: string
  status: QuizQuestionStatus
  questionType: QuizQuestionType
  difficulty: QuizDifficulty
  prompt: string
  payload: Record<string, unknown>
  answerKey: Record<string, unknown>
  explanation: string
  category: string | null
  sourceRefs: Record<string, unknown>
  scheduledDate: string | null
  createdAt: string
}

export interface QuizRecapItem {
  quizDate: string
  questionType: QuizQuestionType
  prompt: string
  correctAnswer: string
  explanation: string
  category: string | null
  percentCorrect: number
  totalAnswers: number
  youAnswered: boolean
  youCorrect: boolean | null
}

export interface QuizRecap {
  nextQuizAt: string | null
  items: QuizRecapItem[]
}

export interface QuizSettings {
  enabled: boolean
  activeWeekdays: number[]
  quizTime: string
  timezone: string | null
  windowMinutes: number
  speedGraceMinutes: number
  difficulty: QuizDifficulty
  enabledQuestionTypes: QuizQuestionType[]
  batchLeadDays: number
  lowQueueNudgeThreshold: number
  slackNotifyOpen: boolean
  slackNotifyReveal: boolean
  monthlySpAmount: number
}
