"""
Pre-built prompt template strings — the static building blocks.

Factory methods in factory.py inject dynamic context (language, framework,
metrics, code snippets) into these templates at runtime.
"""

# ── Phase 2: System analysis (LLM reads README + fingerprint) ─────────

SYSTEM_ANALYSIS_TEMPLATE = """You are a senior software architect analyzing an unfamiliar codebase.

## Deterministic Signals
{project_signals}

## README Content
{readme_content}

## Your Task
{task_description}
"""

# ── Phase 3: Diagnostic strategy selection ────────────────────────────

DIAGNOSTIC_STRATEGY_TEMPLATE = """You are selecting a diagnostic strategy for this project.

## Project Profile
{project_profile}

## User's Concern
{user_concern}

## Available Strategies
{strategy_list}

## Your Task
{task_description}
"""

# ── Phase 5: Debate engine ────────────────────────────────────────────

PROPOSER_TEMPLATE = """You are an expert {language} {project_type} diagnostics specialist (Proposer).

## Project Context
{analysis_context}

## Objective
{target_improvement}

## Language-Specific Guidance
{language_guidance}

## Output Format
{output_format}
"""

CRITIQUE_TEMPLATE = """You are a rigorous {language} software architect (Critique).

## Project Context
{analysis_context}

## Proposer's Suggestions
{proposals}

## Review Dimensions
{review_dimensions}

## Output Format
{output_format}
"""

JUDGE_TEMPLATE = """You are a {language} engineering lead (Judge).

## Project Context
{analysis_context}

## Proposer's Suggestions
{proposals}

## Critique Feedback
{critiques}

## Output Format
{output_format}
"""
