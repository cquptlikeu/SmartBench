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
    """Phase 4: Build code graph."""
    try:
        builder = CodeGraphBuilder(max_files=300)
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            task = progress.add_task(f"Building code graph ({fingerprint.primary_language.value})...", total=None)
            graph = builder.build(project_path, fingerprint.primary_language)
            progress.remove_task(task)
        return graph
    except Exception as e:
        console.print(f"  [yellow]Graph build issue: {e}[/yellow]")
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
    console.print("\n[bold]Running multi-agent debate...[/bold]")

    def llm_fn(prompt: str) -> str:
        return _call_llm(api_config, prompt) or ""

    debate_engine = DebateEngine(llm_fn, prompt_factory=factory)
    result = debate_engine.debate(analysis_context, target=concern)

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
    result = debate_engine.debate(analysis_context, target=concern)

    _display_diagnosis_results(result, fingerprint, None)


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


def configure_api_keys() -> Optional[Dict[str, str]]:
    """Interactive API key configuration.

    Behavior (matches user requirement: reconfigure on each terminal restart):
    1. Checks environment variables — offers to use them (quick path)
    2. User can decline env vars and enter keys manually
    3. If no env vars, prompts for manual entry
    4. Keys are stored ONLY in memory (never persisted to disk)
    5. When terminal closes → all state lost → next 'smartbench' re-prompts
    """
    apis = {}

    console.print("\n  [dim]API keys are stored in memory only — restart terminal to reconfigure.[/dim]")
    console.print("  [dim]Press Enter to skip any provider.[/dim]")

    env_keys = {
        "deepseek": os.environ.get("DEEPSEEK_API_KEY", ""),
        "openai": os.environ.get("OPENAI_API_KEY", ""),
        "anthropic": os.environ.get("ANTHROPIC_API_KEY", ""),
        "glm": os.environ.get("GLM_API_KEY", ""),
        "doubao": os.environ.get("DOUBAO_API_KEY", ""),
    }

    used_providers = set()

    # Offer env vars first
    for provider, env_val in env_keys.items():
        if env_val:
            if Confirm.ask(f"  Use ${provider.upper()}_API_KEY from environment?", default=True):
                apis[provider] = env_val
                used_providers.add(provider)
                console.print(f"    [green]OK[/green] {provider}")

    # Always allow manual entry for any remaining providers
    remaining = [p for p in ["deepseek", "openai", "anthropic"] if p not in used_providers]
    if remaining:
        console.print(f"\n  [dim]Enter keys for remaining providers (or press Enter to skip):[/dim]")
        for provider in remaining:
            key = Prompt.ask(f"  {provider} API key", default="", password=True)
            if key:
                base_url = Prompt.ask(f"  {provider} base URL (optional)", default="")
                apis[provider] = key
                if base_url:
                    apis[f"{provider}_base_url"] = base_url
                    console.print(f"    [green]OK[/green] {provider}")

    return apis if apis else None


def _load_api_keys_from_env() -> Optional[Dict[str, str]]:
    """Load API keys from environment variables."""
    apis = {}
    for provider in ["OPENAI", "DEEPSEEK", "GLM", "DOUBAO", "ANTHROPIC"]:
        key = os.environ.get(f"{provider}_API_KEY", "")
        if key:
            apis[provider.lower()] = key
    return apis if apis else None


def _call_llm(api_config: Dict[str, str], prompt: str,
              system: str = "You are an expert software engineer. Respond with ONLY the requested JSON.",
              model: str = "deepseek") -> str:
    """Call an LLM via OpenAI-compatible API."""
    import urllib.request
    import urllib.error

    BASE_URLS = {
        "deepseek": "https://api.deepseek.com/v1",
        "openai": "https://api.openai.com/v1",
        "glm": "https://open.bigmodel.cn/api/paas/v4",
        "doubao": "https://ark.cn-beijing.volces.com/api/v3",
        "anthropic": "https://api.anthropic.com/v1",
    }

    MODEL_NAMES = {
        "deepseek": "deepseek-chat",
        "openai": "gpt-4o",
        "glm": "glm-4-0520",
        "doubao": "doubao-seed-2.0-pro-260215",
        "anthropic": "claude-sonnet-4-20250514",
    }

    order = [model] + [p for p in api_config if p != model and not p.endswith("_base_url")]

    for provider in order:
        api_key = api_config.get(provider)
        if not api_key:
            continue

        base_url = api_config.get(f"{provider}_base_url", BASE_URLS.get(provider, ""))
        model_name = MODEL_NAMES.get(provider, "gpt-3.5-turbo")
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
            error_body = e.read().decode("utf-8", errors="ignore")[:500]
            console.print(f"  [dim]{provider} HTTP {e.code}: {error_body}[/dim]")
            continue
        except Exception as e:
            console.print(f"  [dim]{provider} error: {e}[/dim]")
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
