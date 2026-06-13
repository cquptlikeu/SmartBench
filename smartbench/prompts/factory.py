"""
PromptFactory — builds all prompts dynamically from ProjectFingerprint.

Every prompt is assembled at runtime from the fingerprint, not hardcoded.
This is the key architectural fix: "Raft KV" never appears in engine code.
"""

from typing import Optional, List, Dict, Any
from smartbench.detector.fingerprint import ProjectFingerprint, Language


class PromptFactory:
    """
    Generates all LLM prompts dynamically based on ProjectFingerprint.

    Usage:
        fp = ProjectScanner(path).scan()
        factory = PromptFactory(fp)
        analysis_prompt = factory.build_analysis_prompt(metrics, logs)
        strategy_prompt = factory.build_strategy_prompt(user_concern)
    """

    def __init__(self, fingerprint: ProjectFingerprint):
        self.fp = fingerprint

    # ── Phase 2: Project Understanding ─────────────────────────────────

    def build_project_understanding_prompt(self, readme_content: str = "") -> str:
        """Ask LLM to understand the project from README + fingerprint signals."""
        lang = self.fp.primary_language.value
        fw = self.fp.framework.value
        ptype = self.fp.project_type.value

        base = f"""You are a senior software architect analyzing an unfamiliar codebase.

## Deterministic Signals (from file-system scan)
- **Primary language**: {lang} (confidence: {self.fp.language_confidence:.0%})
- **Secondary languages**: {[l.value for l in self.fp.secondary_languages] or 'none'}
- **Framework**: {fw} (confidence: {self.fp.framework_confidence:.0%})
- **Project type**: {ptype}
- **Build system**: {self.fp.build_system or 'unknown'}
- **Source files**: {self.fp.source_files} (est. ~{self.fp.lines_of_code_estimate:,} LOC)
- **Entry points**: {', '.join(self.fp.entry_points[:5]) or 'none detected'}
- **Dependencies**: {', '.join(self.fp.dependencies[:20]) or 'none detected'}

## Git Signals
- **Is git repo**: {self.fp.is_git_repo}
- **Recent commits**: {self.fp.recent_commit_count}
- **Hot files** (recently changed): {', '.join(self.fp.hot_files[:10]) or 'none'}"""

        if readme_content:
            base += f"""

## README Content
{readme_content[:4000]}"""

        base += """

## Your Task
Based on the signals above, provide a concise analysis in JSON format:
```json
{
  "project_summary": "1-2 sentence summary of what this project does",
  "primary_domain": "web_service / database / distributed_system / cli_tool / ...",
  "key_concerns": ["concern1", "concern2", "concern3"],
  "suggested_diagnostic_focus": "what diagnostic dimensions matter most (performance/correctness/security/architecture)",
  "additional_context_needed": "what else you'd want to know before diagnosing (short answer or 'none')"
}
```
Return ONLY the JSON, no other text."""

        return base

    # ── Phase 3: Strategy Selection ────────────────────────────────────

    def build_strategy_prompt(self, user_concern: str, available_strategies: List[Dict]) -> str:
        """Ask LLM to select and parameterize a diagnostic strategy."""
        lang = self.fp.primary_language.value
        fw = self.fp.framework.value

        strategy_list = "\n".join(
            f"- **{s['name']}**: {s['description']} (tools: {', '.join(s.get('tools', []))})"
            for s in available_strategies
        )

        return f"""You are selecting a diagnostic strategy for a {lang} {fw} project.

## Project
- Language: {lang}
- Framework: {fw}
- Type: {self.fp.project_type.value}
- Est. size: {self.fp.source_files} files, ~{self.fp.lines_of_code_estimate:,} LOC

## User's Concern
{user_concern}

## Available Strategies (pre-validated diagnostic templates)
{strategy_list}

## Your Task
Select the BEST strategy and parameterize it. Return JSON:
```json
{{
  "selected_strategy": "strategy_name",
  "confidence": 0.0_to_1.0,
  "reasoning": "why this strategy fits (1 sentence)",
  "parameter_overrides": {{
    "focus_areas": ["area1"],
    "exclude_patterns": ["pattern1"],
    "custom_thresholds": {{}}
  }},
  "alternative_strategies": ["backup1"],
  "estimated_duration_minutes": 5
}}
```
Return ONLY the JSON."""

    # ── Phase 5: Multi-Agent Debate ────────────────────────────────────

    def build_analysis_context(self, metrics: Optional[Dict] = None,
                                logs: str = "", error_logs: str = "",
                                code_context: str = "",
                                user_symptoms: str = "") -> str:
        """Build the context block injected into all debate prompts."""
        parts = [f"## Project Profile\n"
                 f"- **Name**: {self.fp.project_name}\n"
                 f"- **Language**: {self.fp.primary_language.value}\n"
                 f"- **Framework**: {self.fp.framework.value}\n"
                 f"- **Type**: {self.fp.project_type.value}\n"
                 f"- **Build system**: {self.fp.build_system}\n"]

        if metrics:
            parts.append(f"\n## Performance Metrics\n"
                        f"- QPS: {metrics.get('qps', 'N/A')}\n"
                        f"- Avg Latency: {metrics.get('avg_latency', 'N/A')} ms\n"
                        f"- P99 Latency: {metrics.get('p99_latency', 'N/A')} ms\n"
                        f"- Error Rate: {metrics.get('error_rate', 'N/A')}\n")

        if user_symptoms:
            parts.append(f"\n## Reported Symptoms\n{user_symptoms}\n")

        if code_context:
            parts.append(f"\n## Relevant Code Context\n{code_context[:4000]}\n")

        if logs:
            parts.append(f"\n## Application Logs\n{logs[:2000]}\n")

        if error_logs:
            parts.append(f"\n## Error Logs\n{error_logs[:1500]}\n")

        return "\n".join(parts)

    def build_proposer_prompt(self, analysis_context: str,
                               target_improvement: str = "Identify and fix the most impactful issues") -> str:
        """Generate the Proposer prompt for a specific language/project."""
        lang = self.fp.primary_language.value
        ptype = self.fp.project_type.value

        lang_guidance = self._language_specific_guidance()

        return f"""You are an expert {lang} {ptype} diagnostics specialist (Proposer).

Your job: analyze the project context below and propose specific, actionable fixes or improvements.

{analysis_context}

## Target
{target_improvement}

## Language-Specific Guidance
{lang_guidance}

## Output Requirements
Return a JSON object with your analysis and proposals:
```json
{{
  "analysis": {{
    "root_cause": "concise root cause (max 100 chars)",
    "impact_assessment": "what's affected and how severely"
  }},
  "proposals": [
    {{
      "title": "short descriptive title (max 10 words)",
      "location": "file_path:line_number",
      "problem": "what's wrong (max 150 chars)",
      "solution": "concrete fix, with pseudocode if applicable",
      "implementation_steps": ["step 1", "step 2", "step 3"],
      "expected_improvement": "quantified if possible (e.g. 15% latency reduction)",
      "priority": 1_to_5,
      "risk_level": "low/medium/high"
    }}
  ]
}}
```
Return ONLY the JSON, no other text."""

    def build_critique_prompt(self, proposals_json: str, analysis_context: str) -> str:
        """Generate the Critique prompt."""
        lang = self.fp.primary_language.value

        return f"""You are a rigorous {lang} software architect (Critique).

Your job: review the Proposer's suggestions for correctness, safety, and feasibility.

## Project Context
{analysis_context}

## Proposer's Suggestions
{proposals_json}

## Review Dimensions
1. **Correctness**: Could this fix introduce new bugs?
2. **Safety**: Thread safety, data consistency, error handling
3. **Feasibility**: Is the proposed change realistic given the codebase?
4. **Side Effects**: What else might break?

## Output
Return JSON:
```json
{{
  "verdicts": [
    {{
      "proposal_title": "matching title from proposer",
      "verdict": "accept / modify / reject",
      "concerns": ["concern 1", "concern 2"],
      "suggested_modifications": "if modify: what to change"
    }}
  ],
  "overall_assessment": "summary of review quality and confidence (1 sentence)"
}}
```
Return ONLY the JSON."""

    def build_judge_prompt(self, proposals_json: str, critiques_json: str,
                            analysis_context: str) -> str:
        """Generate the Judge prompt."""
        lang = self.fp.primary_language.value

        return f"""You are a {lang} engineering lead (Judge) making the final call.

## Project Context
{analysis_context}

## Proposer's Suggestions
{proposals_json}

## Critique Feedback
{critiques_json}

## Your Task
Synthesize both perspectives and produce a final, actionable diagnostic report.

Return JSON:
```json
{{
  "decision": "accepted / mixed / rejected",
  "reasoning": "why this decision was reached (max 150 chars)",
  "final_suggestions": [
    {{
      "title": "title",
      "description": "actionable problem + solution description",
      "implementation": "concrete steps to implement",
      "location": "file:line if applicable",
      "priority": 1_to_5,
      "risk_level": "low/medium/high",
      "consensus": "high / medium / low — how much the models agree"
    }}
  ],
  "risk_summary": "top risks to watch for during implementation"
}}
```
Return ONLY the JSON."""

    # ── Language-specific guidance ─────────────────────────────────────

    def _language_specific_guidance(self) -> str:
        """Return language-specific diagnostic hints."""
        lang = self.fp.primary_language

        guidance = {
            Language.PYTHON: (
                "- Check for GIL contention in CPU-bound threads\n"
                "- Watch for asyncio event loop blocking\n"
                "- Use tracemalloc / py-spy for memory profiling\n"
                "- Consider pydantic model overhead in hot paths"
            ),
            Language.GO: (
                "- Use pprof for CPU/memory profiling\n"
                "- Check goroutine leaks with runtime.NumGoroutine()\n"
                "- Watch for channel blocking and select{} deadlocks\n"
                "- Use race detector: go test -race\n"
                "- Consider sync.Pool for allocation-heavy paths"
            ),
            Language.RUST: (
                "- Check for unnecessary .clone() calls\n"
                "- Watch for async task spawning without joining\n"
                "- Use cargo-flamegraph for CPU profiling\n"
                "- Consider lock contention: std::sync::Mutex vs tokio::sync::Mutex"
            ),
            Language.CPP: (
                "- Use perf + FlameGraph for CPU profiling\n"
                "- Check for memory leaks with Valgrind/ASAN\n"
                "- Watch for lock contention in multi-threaded paths\n"
                "- Consider move semantics and copy elision opportunities\n"
                "- Check for virtual function dispatch overhead in hot paths"
            ),
            Language.JAVA: (
                "- Use JFR (Java Flight Recorder) for profiling\n"
                "- Check GC pause times and allocation rates\n"
                "- Watch for thread pool exhaustion\n"
                "- Use Arthas for live diagnosis"
            ),
            Language.JAVASCRIPT: (
                "- Use clinic.js / 0x for flame graphs\n"
                "- Check for Promise.all() missing error handlers\n"
                "- Watch for event loop blocking with synchronous I/O\n"
                "- Use --inspect + Chrome DevTools for CPU profiling"
            ),
            Language.TYPESCRIPT: (
                "- Same as JavaScript, plus:\n"
                "- Check for excessive type inference overhead\n"
                "- Watch for decorator overhead in NestJS"
            ),
            Language.RUBY: (
                "- Use ruby-prof / stackprof for CPU profiling\n"
                "- Check for N+1 queries in ActiveRecord\n"
                "- Watch for memory bloat from object allocations\n"
                "- Use rbtrace for live method tracing"
            ),
            Language.SWIFT: (
                "- Use Instruments (Time Profiler, Allocations) for profiling\n"
                "- Check for retain cycles causing memory leaks\n"
                "- Watch for main thread blocking\n"
                "- Use swift-concurrency checks for actor isolation"
            ),
            Language.CSHARP: (
                "- Use dotnet-trace / PerfView for CPU profiling\n"
                "- Check for async/await deadlocks (ConfigureAwait)\n"
                "- Watch for LINQ materialization overhead\n"
                "- Use dotnet-counters for live metrics"
            ),
            Language.KOTLIN: (
                "- Reuses JVM tools: JFR, jstack, jmap\n"
                "- Check for coroutine cancellation leaks\n"
                "- Watch for unnecessary object boxing\n"
                "- Use kotlinx-benchmark for microbenchmarks"
            ),
            Language.ZIG: (
                "- Use valgrind + kcachegrind for profiling\n"
                "- Check for undefined behavior with zig test\n"
                "- Watch for allocator mismatches\n"
                "- Use std.testing.expectApproxEqRel for float comparisons"
            ),
        }

        return guidance.get(lang, "- Use standard profiling tools for this language\n"
                            "- Check for common concurrency and memory issues")
