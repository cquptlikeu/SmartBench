"""
SmartBench CLI — interactive code diagnosis wizard.

Usage:
    smartbench              # Interactive mode (full wizard)
    smartbench quick        # Quick mode (minimal questions, auto-detect everything)
    smartbench diagnose     # Just diagnose (skip benchmarking for non-perf issues)
"""

import sys
import os
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

# Ensure package import works
sys.path.insert(0, str(Path(__file__).parent.parent))

from smartbench.detector.scanner import ProjectScanner
from smartbench.detector.fingerprint import ProjectFingerprint, Language, Framework
from smartbench.prompts.factory import PromptFactory
from smartbench.graph.builder import CodeGraphBuilder
from smartbench.graph.retriever import GraphRetriever
from smartbench.diagnostics.registry import DiagnosticRegistry, ProblemCategory
from smartbench.diagnostics.tools import ALL_TOOLS
from smartbench.engine.debate import DebateEngine, DebateResult

app = typer.Typer(
    name="smartbench",
    help="SmartBench — AI-powered universal code diagnosis tool",
    add_completion=False,
)
console = Console()


# ═══════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    quick: bool = typer.Option(False, "--quick", "-q", help="Quick mode: auto-detect everything"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project path or git URL"),
    concern: Optional[str] = typer.Option(None, "--concern", "-c", help="What problem are you facing?"),
):
    """SmartBench — AI-powered universal code diagnosis tool."""
    if ctx.invoked_subcommand is None:
        if quick:
            run_quick_mode(project, concern)
        else:
            run_interactive_wizard()


@app.command()
def quick(
    project: Optional[str] = typer.Option(None, "--project", "-p"),
    concern: Optional[str] = typer.Option(None, "--concern", "-c"),
):
    """Quick diagnosis — auto-detect everything, minimal prompts."""
    run_quick_mode(project, concern)


@app.command()
def diagnose(
    project: str = typer.Option(..., "--project", "-p"),
    symptoms: Optional[str] = typer.Option(None, "--symptoms", "-s"),
    performance: bool = typer.Option(False, "--perf", help="Performance profiling mode"),
):
    """Run diagnosis only (no benchmarking)."""
    run_diagnose_mode(project, symptoms, performance)


@app.command()
def check():
    """Check tool availability for the current system."""
    from smartbench.detector.scanner import ProjectScanner
    current = os.getcwd()
    try:
        fp = ProjectScanner(current).scan()
        registry = DiagnosticRegistry()
        for tool in ALL_TOOLS:
            registry.register(tool)
        health = registry.health_check(fp.primary_language)
        table = Table("Tool", "Available", "Language")
        for name, available in health.items():
            tool = registry.get_tool(name)
            langs = ", ".join(l.value for l in tool.applicable_languages[:3]) if tool else ""
            table.add_row(name, "[green]OK[/green]" if available else "[red]NO[/red]", langs)
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# ═══════════════════════════════════════════════════════════════════════
# Interactive Wizard
# ═══════════════════════════════════════════════════════════════════════

def run_interactive_wizard():
    """Full interactive setup wizard."""
    console.print()
    console.print(Panel.fit(
        "[bold cyan]SmartBench[/bold cyan] — Universal Code Diagnosis\n"
        "[dim]AI-powered analysis for any codebase, any language[/dim]",
        border_style="cyan",
    ))

    # ── Step 1: Project source ────────────────────────────────────────
    console.print("\n[bold]Step 1/4[/bold] — Where is your code?")
    console.print("  Enter a local path or a git repository URL.")
    console.print("  [dim]Examples: /home/user/myproject  |  https://github.com/user/repo[/dim]")

    project_input = Prompt.ask("  Project path/URL").strip()

    project_path = resolve_project_path(project_input)
    if not project_path:
        console.print(f"[red]Cannot access: {project_input}[/red]")
        raise typer.Exit(1)

    console.print(f"  [green]OK[/green] Project: {project_path}")

    # ── Step 2: API keys ──────────────────────────────────────────────
    console.print("\n[bold]Step 2/4[/bold] — Configure LLM API keys")
    console.print("  SmartBench needs at least one LLM API key to analyze your code.")

    api_config = configure_api_keys()
    if not api_config:
        console.print("[red]No API keys configured. SmartBench requires an LLM to function.[/red]")
        raise typer.Exit(1)

    # ── Step 3: Project detection ─────────────────────────────────────
    console.print("\n[bold]Step 3/4[/bold] — Analyzing your project...")
    fingerprint = run_phase1_detection(project_path)
    _display_fingerprint(fingerprint)

    # Phase 2: LLM reads README
    readme_content = ""
    if fingerprint.has_readme:
        try:
            readme_content = (Path(project_path) / fingerprint.readme_path).read_text(
                encoding="utf-8", errors="ignore"
            )[:4000]
        except Exception:
            pass

    if api_config and readme_content:
        console.print("\n  [dim]Asking LLM to understand your project...[/dim]")
        factory = PromptFactory(fingerprint)
        prompt = factory.build_project_understanding_prompt(readme_content)
        response = _call_llm(api_config, prompt)
        if response:
            understanding = _parse_json_safe(response)
            if understanding:
                _display_project_understanding(understanding)

    # ── Step 4: Clarify concern ───────────────────────────────────────
    console.print("\n[bold]Step 4/4[/bold] — What would you like to diagnose?")
    console.print("  [dim]performance, crashes, memory leaks, code quality, security, or 'analyze everything'[/dim]")
    user_concern = Prompt.ask("  Concern", default="analyze the project for issues").strip()

    # ── Build code graph ──────────────────────────────────────────────
    console.print("\n[bold]Building code graph...[/bold]")
    graph = run_phase4_graph(project_path, fingerprint)

    if graph and len(graph.nodes) > 0:
        console.print(f"  [green]OK[/green] {graph.summary()}")
        run_diagnosis_with_graph(project_path, fingerprint, graph, api_config, user_concern)
    else:
        console.print("  [yellow]Could not build code graph (no source files found?)[/yellow]")
        run_fallback_analysis(project_path, fingerprint, api_config, user_concern)

    console.print("\n[bold green]Done![/bold green]")
    console.print("  Thanks for using SmartBench!\n")


# ═══════════════════════════════════════════════════════════════════════
# Quick Mode
# ═══════════════════════════════════════════════════════════════════════

def run_quick_mode(project: Optional[str] = None, concern: Optional[str] = None):
    """Minimal-interaction quick mode."""
    console.print(Panel.fit("[bold cyan]SmartBench Quick Mode[/bold cyan]", border_style="cyan"))

    if not project:
        project = Prompt.ask("Project path/URL").strip()

    project_path = resolve_project_path(project)
    if not project_path:
        console.print(f"[red]Cannot access: {project}[/red]")
        raise typer.Exit(1)

    api_config = _load_api_keys_from_env()
    if not api_config:
        console.print("[yellow]No API keys in environment — some features disabled[/yellow]")

    fingerprint = run_phase1_detection(project_path)
    _display_fingerprint(fingerprint)

    if not concern:
        concern = "analyze the project for potential issues"

    graph = run_phase4_graph(project_path, fingerprint)
    if graph:
        run_diagnosis_with_graph(project_path, fingerprint, graph, api_config, concern)
    else:
        run_fallback_analysis(project_path, fingerprint, api_config, concern)

    console.print("\n[bold green]Done![/bold green]\n")


def run_diagnose_mode(project: str, symptoms: Optional[str], performance: bool):
    """Diagnosis-only mode."""
    project_path = resolve_project_path(project)
    if not project_path:
        console.print(f"[red]Cannot access: {project}[/red]")
        raise typer.Exit(1)

    api_config = _load_api_keys_from_env()
    fingerprint = run_phase1_detection(project_path)
    _display_fingerprint(fingerprint)

    category = ProblemCategory.PERFORMANCE if performance else ProblemCategory.UNKNOWN
    registry = DiagnosticRegistry()
    for tool in ALL_TOOLS:
        registry.register(tool)

    results = registry.diagnose(fingerprint.primary_language, category, str(project_path))

    console.print("\n[bold]Diagnostic Results:[/bold]")
    for r in results:
        if r.success and r.symptoms:
            console.print(f"  [green]OK[/green] {r.tool_name}: {len(r.symptoms)} findings")
            for s in r.symptoms:
                console.print(f"    - {s}")
            for sug in r.suggestions:
                console.print(f"    [cyan]tip[/cyan] {sug.get('title', '')}")
                if sug.get("command"):
                    console.print(f"      [dim]{sug['command']}[/dim]")
        elif not r.success:
            console.print(f"  [dim]--[/dim] {r.tool_name}: {r.error or 'not available'}")

    # Health check
    console.print("\n[bold]Tool Availability:[/bold]")
    health = registry.health_check(fingerprint.primary_language)
    table = Table("Tool", "Available")
    for name, available in health.items():
        table.add_row(name, "[green]yes[/green]" if available else "[red]no[/red]")
    console.print(table)


# ═══════════════════════════════════════════════════════════════════════
# Phase Implementations
# ═══════════════════════════════════════════════════════════════════════

def run_phase1_detection(project_path: str) -> ProjectFingerprint:
    """Phase 1: Deterministic project scanning (zero LLM)."""
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Scanning project files...", total=None)
        scanner = ProjectScanner(project_path)
        fp = scanner.scan()
        progress.remove_task(task)
    return fp


def run_phase4_graph(project_path: str, fingerprint: ProjectFingerprint):
    """Phase 4: Build code graph — parses primary + secondary languages."""
    try:
        builder = CodeGraphBuilder(max_files=500)
        all_langs = [fingerprint.primary_language] + fingerprint.secondary_languages

        if len(all_langs) == 1:
            lang_label = fingerprint.primary_language.value
        else:
            lang_label = " + ".join(l.value for l in all_langs)

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            task = progress.add_task(f"构建代码图 ({lang_label})...", total=None)

            main_graph = builder.build(project_path, fingerprint.primary_language)

            # Also parse secondary languages and merge
            for sec_lang in fingerprint.secondary_languages:
                sec_graph = builder.build(project_path, sec_lang)
                if sec_graph and len(sec_graph.nodes) > 0:
                    main_graph = main_graph.merge(sec_graph)

            progress.remove_task(task)

        # Show language breakdown
        lang_counts = {}
        for node in main_graph.nodes.values():
            lang = node.language or "unknown"
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
        if len(lang_counts) > 1:
            breakdown = ", ".join(f"{l}:{c}" for l, c in sorted(lang_counts.items()))
            console.print(f"    [dim]语言分布: {breakdown}[/dim]")

        return main_graph
    except Exception as e:
        console.print(f"  [yellow]代码图构建问题: {e}[/yellow]")
        return None


def run_diagnosis_with_graph(project_path: str, fingerprint: ProjectFingerprint,
                              graph, api_config: Optional[Dict],
                              concern: str):
    """Run the full graph-enhanced diagnosis pipeline."""
    if not api_config:
        console.print("[yellow]No LLM configured — showing graph stats only[/yellow]")
        _display_graph_stats(graph, fingerprint)
        return

    factory = PromptFactory(fingerprint)

    # Phase 3: Strategy selection
    strategies = [
        {"name": "performance_analysis", "description": "CPU, memory, I/O profiling",
         "tools": ["perf", "pprof", "flamegraph"]},
        {"name": "correctness_audit", "description": "Bug detection, edge cases, error handling",
         "tools": ["static_analysis", "test_coverage"]},
        {"name": "architecture_review", "description": "Design patterns, coupling, cohesion",
         "tools": ["dependency_analysis", "code_graph"]},
        {"name": "security_scan", "description": "Vulnerabilities, injection, secrets exposure",
         "tools": ["static_analysis", "dependency_audit"]},
    ]

    if fingerprint.hot_files:
        strategies.append({
            "name": "hotspot_analysis",
            "description": f"Focus on recently changed files: {', '.join(fingerprint.hot_files[:3])}",
            "tools": ["code_graph", "git_blame"],
        })

    strategy_prompt = factory.build_strategy_prompt(concern, strategies)
    strategy_response = _call_llm(api_config, strategy_prompt)
    strategy = _parse_json_safe(strategy_response) if strategy_response else None

    if strategy:
        selected = strategy.get("selected_strategy", "auto")
        reasoning = strategy.get("reasoning", "")
        console.print(f"\n  [cyan]Strategy:[/cyan] {selected}")
        if reasoning:
            console.print(f"  [dim]{reasoning}[/dim]")

    # Graph-enhanced context retrieval
    retriever = GraphRetriever(graph, project_path, max_tokens_estimate=4000)
    code_context = retriever.retrieve(concern)

    analysis_context = factory.build_analysis_context(
        code_context=code_context,
        user_symptoms=concern,
    )

    # Phase 5: Multi-agent debate
    console.print("\n[bold]多 Agent 辩论中...[/bold]\n")

    def llm_fn(prompt: str) -> str:
        return _call_llm(api_config, prompt) or ""

    debate_engine = DebateEngine(llm_fn, prompt_factory=factory)
    result = debate_engine.debate(analysis_context, target=concern,
                                  on_progress=_show_debate_round)

    _display_diagnosis_results(result, fingerprint, graph)


def run_fallback_analysis(project_path: str, fingerprint: ProjectFingerprint,
                           api_config: Optional[Dict], concern: str):
    """Fallback: file-based analysis when code graph can't be built."""
    if not api_config:
        console.print("[yellow]No LLM configured — cannot perform analysis[/yellow]")
        return

    factory = PromptFactory(fingerprint)

    code_context = ""
    for entry_file in fingerprint.entry_points[:3]:
        try:
            content = (Path(project_path) / entry_file).read_text(
                encoding="utf-8", errors="ignore"
            )
            code_context += f"\n// {entry_file}\n{content[:2000]}\n"
        except Exception:
            pass

    if fingerprint.has_readme:
        try:
            readme = (Path(project_path) / fingerprint.readme_path).read_text(
                encoding="utf-8", errors="ignore"
            )
            code_context = f"// {fingerprint.readme_path}\n{readme[:2000]}\n" + code_context
        except Exception:
            pass

    analysis_context = factory.build_analysis_context(
        code_context=code_context,
        user_symptoms=concern,
    )

    def llm_fn(prompt: str) -> str:
        return _call_llm(api_config, prompt) or ""

    debate_engine = DebateEngine(llm_fn, prompt_factory=factory)
    result = debate_engine.debate(analysis_context, target=concern,
                                  on_progress=_show_debate_round)

    _display_diagnosis_results(result, fingerprint, None)


def _show_debate_round(role: str, parsed_json: Optional[Dict], raw_text: str):
    """辩论每轮结束后调用 — 用 Rich Panel 显示 LLM 产出。"""
    role_names = {
        "proposer": ("Proposer（方案提出者）", "cyan"),
        "critique": ("Critique（交叉审查者）", "yellow"),
        "judge": ("Judge（最终仲裁者）", "green"),
    }
    display_name, color = role_names.get(role, (role, "white"))

    if not parsed_json:
        console.print(Panel(
            f"[red]解析失败[/red]\n[dim]{raw_text[:300] if raw_text else '(无输出)'}[/dim]",
            title=f"[{color}]{display_name}[/{color}]",
            border_style=color,
        ))
        return

    if role == "proposer":
        analysis = parsed_json.get("analysis", {})
        proposals = parsed_json.get("proposals", [])
        body = f"[bold]根因分析：[/bold]{analysis.get('root_cause', 'N/A')}\n"
        body += f"[bold]影响评估：[/bold]{analysis.get('impact_assessment', 'N/A')}\n\n"
        for i, p in enumerate(proposals[:5], 1):
            body += f"[bold]#{i} {p.get('title', '无标题')}[/bold] [{p.get('risk_level', '?')}风险]\n"
            body += f"  {p.get('problem', '')[:120]}\n"
            body += f"  [dim]位置: {p.get('location', '?')}[/dim]\n"
        console.print(Panel(body.strip(), title=f"[{color}]{display_name}[/{color}] "
                           f"（{len(proposals)} 条方案）", border_style=color))

    elif role == "critique":
        verdicts = parsed_json.get("verdicts", [])
        assessment = parsed_json.get("overall_assessment", "")
        body = ""
        for v in verdicts:
            icon = {"accept": "[接受]", "modify": "[需修改]", "reject": "[拒绝]"}.get(
                v.get("verdict", ""), "[?]")
            body += f"{icon} [bold]{v.get('proposal_title', '?')}[/bold]\n"
            for concern in v.get("concerns", []):
                body += f"   └ {concern}\n"
            if v.get("suggested_modifications"):
                body += f"   [dim]建议: {v['suggested_modifications']}[/dim]\n"
        if assessment:
            body += f"\n[dim]{assessment}[/dim]"
        console.print(Panel(body.strip(), title=f"[{color}]{display_name}[/{color}]",
                           border_style=color))

    elif role == "judge":
        decision = parsed_json.get("decision", "?")
        reasoning = parsed_json.get("reasoning", "")
        final = parsed_json.get("final_suggestions", [])
        risk = parsed_json.get("risk_summary", "")
        body = f"[bold]决策：[/bold]{decision}\n"
        body += f"[bold]理由：[/bold]{reasoning}\n"
        body += f"[bold]最终建议：[/bold]{len(final)} 条\n\n"
        for i, s in enumerate(final[:5], 1):
            prio = s.get("priority", 3)
            body += f"[bold]#{i} {s.get('title', '?')}[/bold] [优先级:{prio}] [共识:{s.get('consensus', '?')}]\n"
        if risk:
            body += f"\n[bold red][!] 顶层风险：[/bold red]{risk}"
        console.print(Panel(body.strip(), title=f"[{color}]{display_name}[/{color}] "
                           f"（最终报告）", border_style=color))


# ═══════════════════════════════════════════════════════════════════════
# Display helpers
# ═══════════════════════════════════════════════════════════════════════

def _display_fingerprint(fp: ProjectFingerprint):
    """Display project fingerprint in a table."""
    table = Table(title="Project Fingerprint (Phase 1 — zero LLM)", show_header=False)
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Primary Language", f"[bold]{fp.primary_language.value}[/bold] "
                  f"(confidence: {fp.language_confidence:.0%})")
    if fp.secondary_languages:
        table.add_row("Secondary", ", ".join(l.value for l in fp.secondary_languages))
    table.add_row("Framework", f"{fp.framework.value} (confidence: {fp.framework_confidence:.0%})")
    table.add_row("Project Type", fp.project_type.value)
    table.add_row("Build System", fp.build_system or "unknown")
    table.add_row("Source Files", f"{fp.source_files} (~{fp.lines_of_code_estimate:,} LOC)")
    table.add_row("Entry Points", ", ".join(fp.entry_points[:5]) or "none")
    table.add_row("Dependencies", f"{fp.dependency_count} packages")
    table.add_row("Git", f"{'yes ' + fp.git_remote_url[:50] if fp.is_git_repo else 'no'}")
    if fp.hot_files:
        table.add_row("Hot Files", ", ".join(fp.hot_files[:5]))
    table.add_row("README", f"{'yes: ' + fp.readme_path if fp.has_readme else 'no'}")

    console.print(table)


def _display_project_understanding(understanding: Dict):
    """Display LLM's understanding of the project."""
    console.print("\n[bold cyan]LLM Analysis:[/bold cyan]")
    console.print(f"  [bold]Summary:[/bold] {understanding.get('project_summary', 'N/A')}")
    console.print(f"  [bold]Domain:[/bold] {understanding.get('primary_domain', 'N/A')}")
    concerns = understanding.get("key_concerns", [])
    if concerns:
        console.print(f"  [bold]Key Concerns:[/bold] {', '.join(concerns)}")
    console.print(f"  [bold]Suggested Focus:[/bold] {understanding.get('suggested_diagnostic_focus', 'N/A')}")


def _display_diagnosis_results(result: DebateResult, fp: ProjectFingerprint, graph=None):
    """Display the final diagnosis report."""
    console.print(f"\n[bold]Diagnostic Report[/bold] ({result.duration_ms}ms, {result.iterations} debate rounds)")

    if not result.final_suggestions:
        console.print("  [yellow]No issues identified[/yellow]")
        if graph:
            _display_graph_stats(graph, fp)
        return

    console.print(f"\n[bold green]{len(result.final_suggestions)} findings:[/bold green]\n")

    prio_colors = {5: "red", 4: "yellow", 3: "cyan", 2: "blue", 1: "dim"}

    for i, sug in enumerate(result.final_suggestions, 1):
        title = sug.get("title", f"Finding {i}")
        desc = sug.get("description", "")
        impl = sug.get("implementation", "")
        priority = sug.get("priority", 3)
        risk = sug.get("risk_level", "medium")
        location = sug.get("location", "")
        consensus = sug.get("consensus", "unknown")

        color = prio_colors.get(priority, "white")
        loc_line = f"[bold]Location:[/bold] {location}" if location else ""

        console.print(Panel(
            f"[bold]{title}[/bold]\n\n{desc}\n\n[bold]Fix:[/bold] {impl}\n{loc_line}".strip(),
            title=f"#{i} [{color}]Priority {priority}[/{color}] | Risk: {risk} | Consensus: {consensus}",
            border_style=color,
        ))

    if graph:
        _display_graph_stats(graph, fp)


def _display_graph_stats(graph, fp: ProjectFingerprint):
    """Show code graph statistics."""
    console.print(f"\n  [dim]Code graph: {graph.summary()}[/dim]")


# ═══════════════════════════════════════════════════════════════════════
# Utility functions
# ═══════════════════════════════════════════════════════════════════════

def resolve_project_path(input_path: str) -> Optional[str]:
    """Resolve a project path or git URL to a local directory."""
    import tempfile
    import subprocess

    input_path = os.path.expanduser(input_path)

    local = Path(input_path)
    if local.exists() and local.is_dir():
        return str(local.resolve())

    # Git URL
    if input_path.startswith(("http://", "https://", "git@", "ssh://")):
        console.print("  [dim]Cloning repository...[/dim]")
        tmpdir = os.path.join(tempfile.gettempdir(), f"smartbench_{int(time.time())}")
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", input_path, tmpdir],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                return tmpdir
            console.print(f"  [red]Clone failed: {result.stderr[:200]}[/red]")
        except Exception as e:
            console.print(f"  [red]Clone error: {e}[/red]")

    return None


# ═══════════════════════════════════════════════════════════════════════
# Provider Registry — auto-detects base URL + provider from model name
# ═══════════════════════════════════════════════════════════════════════

PROVIDER_REGISTRY = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "patterns": ["deepseek"],
        "display": "DeepSeek",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "patterns": ["gpt-", "o1-", "o3-", "o4-"],
        "display": "OpenAI",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "patterns": ["claude-"],
        "display": "Anthropic",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "patterns": ["glm-", "chatglm", "cogview"],
        "display": "Zhipu GLM",
    },
    "doubao": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "patterns": ["doubao-", "seed-"],
        "display": "ByteDance Doubao",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "patterns": ["moonshot-", "kimi"],
        "display": "Moonshot Kimi",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "patterns": ["qwen-", "qwq-"],
        "display": "Alibaba Qwen",
    },
    "local": {
        "base_url": "http://localhost:11434/v1",
        "patterns": ["llama", "mistral", "qwen2", "codellama", "deepseek-r1"],
        "display": "Local (Ollama-compatible)",
    },
}


def _detect_provider(model_name: str) -> tuple:
    """Given a model name, return (provider_key, base_url, display_name)."""
    model_lower = model_name.lower().strip()
    for key, info in PROVIDER_REGISTRY.items():
        for pattern in info["patterns"]:
            if model_lower.startswith(pattern):
                return (key, info["base_url"], info["display"])
    # Fallback: treat as OpenAI-compatible generic
    return ("openai", "https://api.openai.com/v1", "OpenAI-compatible")


def masked_input(prompt_text: str) -> str:
    """Read a secret with * echo for each character typed.

    Shows one * per character as the user types, then reveals last 4 chars
    after submission so the user knows their input was registered.
    """
    import sys as _sys

    console.print(f"  {prompt_text}: ", end="")

    if _sys.platform == "win32":
        import msvcrt
        chars = []
        while True:
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                console.print()
                break
            if ch == "\x08":  # backspace
                if chars:
                    chars.pop()
                    console.print("\b \b", end="")
                continue
            if ch == "\x03":  # Ctrl+C
                raise KeyboardInterrupt
            chars.append(ch)
            console.print("*", end="")
        value = "".join(chars)
    else:
        import termios
        import tty
        fd = _sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            chars = []
            while True:
                ch = _sys.stdin.read(1)
                if ch in ("\r", "\n"):
                    console.print()
                    break
                if ch == "\x7f":  # backspace
                    if chars:
                        chars.pop()
                        console.print("\b \b", end="")
                    continue
                if ch == "\x03":  # Ctrl+C
                    raise KeyboardInterrupt
                chars.append(ch)
                console.print("*", end="")
            value = "".join(chars)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    # Show masked confirmation
    if value:
        mask = value[:3] + "****" + value[-4:] if len(value) > 10 else "****"
        console.print(f"    [dim]saved: {mask}[/dim]")
    return value


def configure_api_keys() -> Optional[Dict[str, str]]:
    """Interactive model + API key configuration.

    User only needs to provide:
      1. Model name (e.g. deepseek-chat, gpt-4o, claude-sonnet-4)
      2. API key (masked input with * echo)

    Everything else (provider, base URL) is auto-detected from the
    built-in PROVIDER_REGISTRY.

    Keys stored in memory only — never persisted to disk.
    """
    models_list = []

    console.print("\n  [dim]Keys stored in memory only — restart terminal to reconfigure.[/dim]")

    # Check environment variables first
    env_providers = {
        "deepseek": os.environ.get("DEEPSEEK_API_KEY", ""),
        "openai": os.environ.get("OPENAI_API_KEY", ""),
        "anthropic": os.environ.get("ANTHROPIC_API_KEY", ""),
        "glm": os.environ.get("GLM_API_KEY", ""),
        "doubao": os.environ.get("DOUBAO_API_KEY", ""),
        "moonshot": os.environ.get("MOONSHOT_API_KEY", ""),
        "qwen": os.environ.get("DASHSCOPE_API_KEY", ""),
    }

    for provider, key in env_providers.items():
        if key:
            info = PROVIDER_REGISTRY.get(provider, {})
            display = info.get("display", provider)
            if Confirm.ask(f"  Use ${provider.upper()}_API_KEY from env? ({display})", default=True):
                models_list.append({
                    "provider": provider,
                    "model": "auto",  # will be filled by _call_llm
                    "api_key": key,
                    "base_url": info.get("base_url", ""),
                })
                console.print(f"    [green]OK[/green] {display}")

    # Manual entry
    console.print(f"\n  [bold]Configure your models:[/bold]")
    console.print(f"  [dim]One model is enough — debate engine reuses it for all three roles.[/dim]")
    console.print(f"  [dim]Examples: deepseek-chat | gpt-4o | claude-sonnet-4 | glm-4[/dim]")
    console.print(f"")

    while True:
        if models_list:
            # Already added at least one model — user can stop or add more
            model = Prompt.ask(
                f"  Model name ([green]{len(models_list)} configured[/green], Enter to finish)",
                default="",
            ).strip()
            if not model:
                break
        else:
            model = Prompt.ask("  Model name", default="").strip()
            if not model:
                console.print("    [yellow]At least one model is required.[/yellow]")
                continue

        provider_key, base_url, display = _detect_provider(model)

        # Confirm auto-detection, allow override
        console.print(f"    [dim]Provider: {display} → {base_url}[/dim]")
        override = Prompt.ask(f"    Base URL (Enter to confirm)", default="").strip()
        if override:
            base_url = override

        key = masked_input(f"    API key for {model}")
        if not key:
            console.print("    [yellow]Skipped (no key)[/yellow]")
            continue

        models_list.append({
            "provider": provider_key,
            "model": model,
            "api_key": key,
            "base_url": base_url,
        })
        console.print(f"    [green]OK[/green] {model} ({display}) — {len(models_list)} model(s) total")

    if not models_list:
        return None

    console.print(f"\n  [green]Ready![/green] {len(models_list)} model(s) configured.")
    if len(models_list) == 1:
        console.print(f"  [dim]The debate Proposer/Critique/Judge will all use {models_list[0]['model']}.[/dim]")

    return {"models": models_list}


def _load_api_keys_from_env() -> Optional[Dict[str, str]]:
    """Load API keys from environment variables (quick mode)."""
    models = []
    env_map = {
        "DEEPSEEK_API_KEY": ("deepseek", "deepseek-chat"),
        "OPENAI_API_KEY": ("openai", "gpt-4o"),
        "ANTHROPIC_API_KEY": ("anthropic", "claude-sonnet-4-20250514"),
        "GLM_API_KEY": ("glm", "glm-4-0520"),
        "DOUBAO_API_KEY": ("doubao", "doubao-seed-2.0-pro-260215"),
        "MOONSHOT_API_KEY": ("moonshot", "moonshot-v1-8k"),
        "DASHSCOPE_API_KEY": ("qwen", "qwen-max"),
    }
    for env_var, (provider, default_model) in env_map.items():
        key = os.environ.get(env_var, "")
        if key:
            info = PROVIDER_REGISTRY.get(provider, {})
            models.append({
                "provider": provider,
                "model": default_model,
                "api_key": key,
                "base_url": info.get("base_url", ""),
            })
    return {"models": models} if models else None


def _call_llm(api_config: Dict, prompt: str,
              system: str = "你是一位资深软件工程师。请用中文回复。只返回要求的 JSON，不要其他内容。",
              prefer_provider: str = "") -> str:
    """Call an LLM via OpenAI-compatible API.

    Args:
        api_config: {"models": [{"provider":..., "model":..., "api_key":..., "base_url":...}, ...]}
        prompt: The user prompt
        system: System prompt
        prefer_provider: Try this provider first (e.g. "deepseek"), then fall back to others
    """
    import urllib.request
    import urllib.error

    models = api_config.get("models", [])

    # Fallback: old format {provider: key, ...}
    if not models and isinstance(api_config, dict):
        # Convert old format to new
        for provider in ["deepseek", "openai", "anthropic", "glm", "doubao"]:
            key = api_config.get(provider, "")
            if key:
                info = PROVIDER_REGISTRY.get(provider, {})
                models.append({
                    "provider": provider,
                    "model": "auto",
                    "api_key": key,
                    "base_url": info.get("base_url", ""),
                })

    if not models:
        return ""

    # Order: prefer_provider first, then rest
    ordered = sorted(models, key=lambda m: 0 if m["provider"] == prefer_provider else 1)

    for m in ordered:
        api_key = m.get("api_key", "")
        if not api_key:
            continue

        base_url = m.get("base_url", "").rstrip("/")
        model_name = m.get("model", "auto")
        # If model is "auto", try to guess from provider
        if model_name == "auto":
            defaults = {"deepseek": "deepseek-chat", "openai": "gpt-4o",
                       "glm": "glm-4-0520", "doubao": "doubao-seed-2.0-pro-260215",
                       "anthropic": "claude-sonnet-4-20250514",
                       "moonshot": "moonshot-v1-8k", "qwen": "qwen-max"}
            model_name = defaults.get(m["provider"], "gpt-3.5-turbo")

        url = f"{base_url}/chat/completions"

        body = json.dumps({
            "model": model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }).encode("utf-8")

        req = urllib.request.Request(url, data=body)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {api_key}")

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="ignore")[:300]
            console.print(f"  [dim]{m['provider']} HTTP {e.code}: {error_body}[/dim]")
            continue
        except Exception as e:
            console.print(f"  [dim]{m['provider']} error: {e}[/dim]")
            continue

    return ""


def _parse_json_safe(raw: str) -> Optional[Dict]:
    """Safely parse JSON from LLM output."""
    import re
    if not raw:
        return None

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


if __name__ == "__main__":
    app()
