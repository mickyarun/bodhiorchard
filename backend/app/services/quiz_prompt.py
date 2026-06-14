# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pure prompt builder for the Company Quiz Game generation agent.

Produces the full instruction prompt for a batch of questions grounded in the
org's own dev data (read live via MCP tools), enforcing difficulty, the enabled
question types, a strict JSON contract, and the non-repetition denylist. Pure
(no I/O) so it's unit-testable; the caller supplies the denylist + count.
"""

from __future__ import annotations

from app.models.quiz_question import QuizDifficulty, QuizQuestionType

# Read-only MCP tools the agent uses to mine real org data for questions.
# Deliberately scoped to the FEATURE REGISTRY ONLY — not BUDs (acceptance-
# criteria minutiae like pixel sizes), not team ownership, not the code graph.
# Features carry product/domain meaning, which is the knowledge worth testing.
QUIZ_MCP_TOOLS: list[str] = [
    "get_features",
]

# Model used for generation (capable, cost-reasonable for once-a-week batches).
QUIZ_MODEL = "sonnet"

# Difficulty is about DEPTH OF UNDERSTANDING, never obscurity of a recalled fact.
_DIFFICULTY_RUBRIC: dict[QuizDifficulty, str] = {
    QuizDifficulty.EASY: "Recall what one of our features does, at a high level.",
    QuizDifficulty.MEDIUM: (
        "Connect a feature to the problem it solves or the capability it provides."
    ),
    QuizDifficulty.HARD: (
        "Distinguish between two similar features, or reason about WHY the product "
        "works the way it does — understanding, not obscure recall."
    ),
    QuizDifficulty.MIXED: "Vary across the batch from medium to hard.",
}

_TYPE_INSTRUCTIONS: dict[QuizQuestionType, str] = {
    QuizQuestionType.MULTIPLE_CHOICE: (
        'multiple_choice: payload={"choices": ["..", "..", "..", ".."]} (exactly 4, '
        'one clearly correct, three plausible distractors); answer_key={"correct_index": <0-3>}.'
    ),
    QuizQuestionType.SCRAMBLE: (
        "scramble: the answer is a FEATURE NAME or domain term (1-3 words), never a "
        "person. The prompt describes what it does; the player unscrambles its name. "
        'payload={"scrambled": "<letters of the answer rearranged>", "kind": "letters"}; '
        'answer_key={"answer": "<the term>"}. The scrambled text MUST be a rearrangement '
        "of exactly the answer's letters (spaces allowed)."
    ),
    QuizQuestionType.FILL_BLANK: (
        'fill_blank: write a prompt with a single blank "____". payload={"hint": "<short hint>"}; '
        'answer_key={"answer": "<canonical answer>", "aliases": ["<accepted variant>", ...]}. '
        "Keep the answer a short, unambiguous token; list common spellings/synonyms as aliases."
    ),
}


def build_batch_prompt(
    *,
    count: int,
    difficulty: QuizDifficulty,
    enabled_types: list[QuizQuestionType],
    denylist: list[str],
) -> str:
    """Build the generation prompt for ``count`` questions across enabled types."""
    type_lines = "\n".join(f"- {_TYPE_INSTRUCTIONS[t]}" for t in enabled_types)
    deny_block = (
        "\n".join(f"- {label}" for label in denylist)
        if denylist
        else "(none yet — this is an early batch)"
    )
    return f"""You are the Company Quiz Master for a software product team. Generate exactly \
{count} questions that test whether someone UNDERSTANDS THE PRODUCT — what our features do, \
the problems they solve, and how the domain works. The goal is for a teammate to LEARN \
something and WANT to answer, not to recall an arbitrary number.

Use `get_features` as your source — each feature has a title, a description, and \
capabilities. Build every question from a feature's *meaning*: what it's for, what it \
does, how it differs from another feature. Never invent facts; if a fact isn't in the \
retrieved feature data, skip it. Do NOT ask about BUDs, tickets, or implementation work \
items — only the product's features and what they do.

GOOD questions (write these):
- "Which of these best describes what the <X> feature does?"
- "What problem does <X> solve / who is it for?"
- "Which capability belongs to <X> (and not to <Y>)?"
- "<feature> and <feature> both touch billing — which one handles refunds?"

BAD questions (NEVER write these — they test trivia, not knowledge):
- Exact sizes, pixel dimensions, default config numbers, thresholds, timeouts.
- File names, function names, variable names, line counts, code-graph stats.
- Dates, version numbers, or "when did X ship".
- ANYTHING about people: who owns / works on / wrote / last changed something.

Difficulty: {difficulty.value} — {_DIFFICULTY_RUBRIC[difficulty]}

Spread the {count} questions across these allowed types:
{type_lines}

DO NOT ask about any of these already-used topics (or close paraphrases):
{deny_block}

For EACH question also provide:
- "explanation": 1-3 sentences teaching what the feature does and WHY it matters, \
citing the source (e.g. "from the Slack Bot feature").
- "category": one short tag — one of "feature", "capability", "domain", "workflow".
- "topic_key": a short stable identifier for the topic, e.g. "feature:slack-bot:purpose" \
or "feature:bug-linker:capability". Two questions must never share a topic_key.
- "source_refs": an object of provenance, e.g. {{"features": ["Slack Bot"]}}.

Respond with STRICT JSON only, no prose, in exactly this shape:
{{"questions": [
  {{"question_type": "multiple_choice", "difficulty": "{difficulty.value}", \
"prompt": "...", "payload": {{...}}, "answer_key": {{...}}, "explanation": "...", \
"category": "...", "topic_key": "...", "source_refs": {{...}}}}
]}}
"""
