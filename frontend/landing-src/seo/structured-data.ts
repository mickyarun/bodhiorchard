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

// JSON-LD structured data for the landing site. Previously inlined in
// index.html; now emitted per-route via useSeo so each blob lives on the page
// whose visible content matches it (SoftwareApplication → Home, FAQPage →
// Methodology, where the questions are also rendered visibly).

import { SITE_ORIGIN } from '../routes-manifest'

export const SOFTWARE_APPLICATION_LD = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: 'Bodhiorchard',
  alternateName: 'Bodhiorchard™',
  description:
    'Bodhiorchard is the open-source reference implementation of Agent-Driven Development — a modern methodology that replaces sprint, scrum, and agile ceremony with 12 specialised AI agents working alongside humans across every phase of the software lifecycle.',
  url: `${SITE_ORIGIN}/`,
  applicationCategory: 'DeveloperApplication',
  applicationSubCategory: 'Project Management',
  operatingSystem: 'macOS, Linux, Windows (WSL2)',
  softwareVersion: '0.1.0',
  license: 'https://www.apache.org/licenses/LICENSE-2.0',
  offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
  author: { '@type': 'Person', name: 'Arun Rajkumar', url: 'https://github.com/mickyarun' },
  sameAs: ['https://github.com/mickyarun/bodhiorchard'],
}

export interface Faq {
  question: string
  answer: string
}

// The visible FAQ on /methodology and the FAQPage JSON-LD are generated from
// this one list so the structured data always matches the rendered content.
export const FAQS: Faq[] = [
  {
    question: 'What is Agent-Driven Development?',
    answer:
      'Agent-Driven Development (ADD) is a way of building software where specialised AI agents drive every phase of the lifecycle — intake, spec, design, tech architecture, implementation, testing, UAT, deployment, retrospective — and humans review, decide, and steer. Bodhiorchard is the open-source reference implementation.',
  },
  {
    question: 'Is Bodhiorchard a self-hosted Jira alternative?',
    answer:
      'Yes — for the workflow layer. Bodhiorchard sits between IDE-side AI coding assistants and traditional PM tools. It is especially relevant to teams looking for an Atlassian DC alternative, since Atlassian is sunsetting new self-hosted Jira licences in March 2026 with full shutdown in 2029.',
  },
  {
    question: 'Does my code leave my machine when I use Bodhiorchard?',
    answer:
      'The data plane is always local — Postgres, embeddings, BUDs, scanned repos, and the audit log all sit on your hardware. Only the LLM prompts leave your machine, and only when you choose a cloud inference mode.',
  },
  {
    question: 'What does BUD mean in Bodhiorchard?',
    answer:
      'BUD stands for Business Understanding Document. Every feature lives in one BUD containing spec, tech spec, test plan, acceptance criteria, and full history — all in markdown.',
  },
  {
    question: "What is Bodhiorchard's licence? Can I use it commercially?",
    answer:
      'Bodhiorchard is licensed under the Apache License 2.0, which permits commercial use including embedding in proprietary products. Contributions require DCO sign-off via git commit -s.',
  },
]

export const FAQ_PAGE_LD = {
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: FAQS.map((f) => ({
    '@type': 'Question',
    name: f.question,
    acceptedAnswer: { '@type': 'Answer', text: f.answer },
  })),
}
