# SmartBench v0.5

**Universal AI-Powered Code Diagnosis Tool** — any language, any framework, any project.

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## What is SmartBench?

SmartBench is a **universal code diagnosis platform** that uses LLM-powered multi-agent debate
to analyze any codebase. Drop it on a Python CLI tool, a Go microservice, a Rust library,
or a Java monolith — it auto-detects the language, builds a code graph, and produces
actionable diagnostic reports.

**Core principle**: SmartBench analyzes and suggests — it never modifies your code.

### The 5-Phase Pipeline

```
$ smartbench
  │
  ├─ Phase 1 ─ Project Fingerprint
  │   Scans filesystem deterministically (zero LLM).
  │   Detects: language, framework, project type, build system, dependencies.
  │
  ├─ Phase 2 ─ LLM Project Understanding (optional)
  │   LLM reads README.md + fingerprint → understands project purpose & domain.
  │
  ├─ Phase 3 ─ Strategy Selection
  │   LLM selects the optimal diagnostic strategy from a pre-validated template library.
  │   (LLM chooses, not invents — constrained to proven strategies.)
  │
  ├─ Phase 4 ─ Code Graph Construction
  │   Builds a call graph + dependency graph from source files.
  │   Graph-enhanced context retrieval: 5-10x more token-efficient than full-file reading.
  │
  └─ Phase 5 ─ Multi-Agent Debate
      Proposer → Critique → Judge pipeline cross-validates findings.
      Output: prioritized, actionable diagnostic report.
```

---

## Quick Start

### Installation

```bash
pip install -e .
# or: pip install smartbench
```

Requires Python 3.10+.

### First Run

```bash
smartbench
```

You'll be guided through a 4-step interactive wizard:

```
Step 1/4 — Where is your code?
  Project path/URL: /path/to/your/project

Step 2/4 — Configure LLM
  Model name: deepseek-chat
  API key for deepseek-chat: **********
  saved: sk-****b3e4
  OK deepseek-chat (DeepSeek)

Step 3/4 — Analyzing your project...
  [python] [fastapi] [web_service] 142 src files (git)

Step 4/4 — What would you like to diagnose?
  Concern: performance issues

  Building code graph... 847 nodes, 4521 edges
  Running multi-agent debate... 3 rounds, ~1850 tokens

  Diagnostic Report:
   - Finding #1: Optimize DB connection pooling (Priority 5)
   - Finding #2: Add Redis caching for hot endpoints (Priority 4)
```

### Quick Mode

Skip the wizard with pre-configured environment variables:

```bash
export DEEPSEEK_API_KEY="sk-your-key"
smartbench --quick -p /path/to/project -c "performance"
```

### Commands

| Command | Description |
|---------|-------------|
| `smartbench` | Full interactive wizard |
| `smartbench quick` | Minimal prompts, auto-detect from env |
| `smartbench diagnose -p <path>` | Diagnosis only (no benchmarking) |
| `smartbench check` | Show available diagnostic tools |

---

## Supported Languages & Frameworks

### Language Detection (14 languages)

| Language | Detection | Code Graph | Language Guidance |
|----------|-----------|------------|-------------------|
| Python | `.py`, `requirements.txt`, `pyproject.toml` | ✅ functions/classes/imports/calls | GIL, asyncio, tracemalloc, py-spy |
| Go | `.go`, `go.mod` | ✅ funcs/structs/interfaces/calls | pprof, race detector, goroutine leaks |
| Rust | `.rs`, `Cargo.toml` | ✅ fns/structs/impls/traits/calls | clone() overhead, async, lock contention |
| C/C++ | `.cpp/.cc/.c/.h`, `CMakeLists.txt` | ✅ functions/classes/structs/calls | GDB, Valgrind, ASAN, perf, flamegraph |
| Java | `.java`, `pom.xml`, `build.gradle` | ✅ methods/classes/interfaces/calls | JFR, jstack, GC analysis, Arthas |
| Kotlin | `.kt/.kts`, `build.gradle.kts` | ✅ funs/classes/calls | JVM tools + coroutine checks |
| JavaScript | `.js/.mjs/.cjs`, `package.json` | ✅ functions/classes/imports/calls | clinic.js, event loop, Promise errors |
| TypeScript | `.ts/.tsx`, `tsconfig.json` | ✅ functions/classes/imports/calls | JS tools + type inference, decorators |
| Ruby | `.rb`, `Gemfile` | ✅ defs/classes/calls | ruby-prof, N+1 queries, memory bloat |
| Swift | `.swift`, `Package.swift` | ✅ funcs/classes/structs/calls | Instruments, retain cycles, main thread |
| C# | `.cs` | ✅ methods/classes/interfaces/calls | dotnet-trace, async deadlocks, LINQ |
| Zig | `.zig`, `build.zig` | ✅ fns/structs/calls | valgrind, UB checks, allocator mismatches |

### Framework Detection (20+ frameworks)

Automatically identifies: FastAPI, Flask, Django, Gin, Echo, Fiber, go-kit, go-zero, Kratos,
Express, NestJS, Next.js, React, Vue, Spring Boot, Axum, Actix, Rocket, gRPC, brpc, and more.

---

## Features

### 1. Multi-Agent Debate Engine

Three-role cross-validation reduces LLM hallucination:

```
Proposer (方案提出者)     →  Analyzes context, generates specific proposals
    ↓
Critique (交叉审查者)     →  Reviews for correctness, safety, side effects
    ↓
Judge (最终仲裁者)        →  Synthesizes into final prioritized recommendations
```

All Prompts are dynamically generated from the project fingerprint
— **zero hardcoded assumptions** about the target project.

### 2. Code Graph Engine

- **AST Parsing**: Regex-based (tree-sitter ready) function/class/call extraction
- **Graph Construction**: Nodes (functions, classes, files) + Edges (calls, imports, contains)
- **Smart Retrieval**: Given a concern like "connection timeout", finds the exact functions
  in the call chain instead of dumping entire files into the LLM context
- **5-10x Token Savings**: Only relevant code context reaches the LLM

### 3. Pluggable Diagnostic Tools

| Category | Tools |
|----------|-------|
| System | dmesg, ps, vmstat |
| Go | pprof, race detector, goroutine profile |
| Python | tracemalloc, py-spy, cProfile, pip check |
| C/C++ | GDB, Valgrind, ASAN, perf, flamegraph |
| Java | JFR, jstack, jmap, Arthas |
| Static Analysis | ruff, mypy, bandit (Python) / go vet, staticcheck (Go) / clippy (Rust) / ESLint (JS) |

### 4. Strategy Selector

LLM chooses from a **pre-validated strategy template library** (not from thin air):

- `performance_analysis` — CPU, memory, I/O profiling
- `correctness_audit` — Bug detection, edge cases, error handling
- `architecture_review` — Design patterns, coupling, cohesion
- `security_scan` — Vulnerability detection, dependency auditing
- `hotspot_analysis` — Focus on recently changed files (git-aware)

### 5. Configuration Lifecycle

- API keys stored **in memory only** — never written to disk
- Each terminal restart → fresh reconfiguration (by design)
- Supports 8 LLM providers with auto-detection from model name
- Masked password input with `****abcd` confirmation

---

## Architecture

```
SmartBench/
├── smartbench/
│   ├── cli.py                      # CLI entry point (typer + rich)
│   ├── detector/                   # Phase 1: Zero-LLM project fingerprinting
│   │   ├── fingerprint.py          #   Language/Framework/ProjectType enums + data model
│   │   └── scanner.py              #   Deterministic filesystem scanner
│   ├── prompts/                    # Phase 2-3-5: Dynamic prompt generation
│   │   ├── factory.py              #   PromptFactory — language-aware prompt builder
│   │   └── templates.py            #   Static template strings
│   ├── graph/                      # Phase 4: Code graph engine
│   │   ├── schema.py               #   CodeGraph/CodeNode/CodeEdge data model
│   │   ├── builder.py              #   AST parser (12 languages) → graph
│   │   └── retriever.py            #   Graph-enhanced context retrieval
│   ├── diagnostics/                # Pluggable diagnostic tools
│   │   ├── registry.py             #   DiagnosticRegistry + DiagnosticTool ABC
│   │   └── tools.py                #   8 concrete tool implementations
│   ├── engine/                     # Analysis engines
│   │   ├── debate.py               #   Generic multi-agent debate engine (v0.5 refactor)
│   │   ├── diagnostic.py           #   Legacy diagnostic engine (retained)
│   │   ├── aggregator.py           #   Suggestion deduplication & ranking
│   │   ├── weight.py               #   Model weight calculation
│   │   ├── cache.py                #   File + analysis cache
│   │   └── regression.py           #   Performance regression tracking
│   ├── agents/                     # Agent orchestration (retained from v0.3)
│   └── plugins/                    # Plugin system
│       ├── models/                 #   LLM provider plugins
│       └── systems/                #   Target system plugins (raft_kv, mysql, redis)
├── config/
│   └── default.yaml                # Default configuration
├── tests/
│   ├── test_*.py                   # Unit tests
│   └── e2e_simulation.py           # Full pipeline mock test
├── pyproject.toml                  # Build config + entry points
└── README.md
```

---

## Configuration

### Model & API Key Setup

SmartBench auto-detects provider and base URL from your model name:

| You type | Auto-detected |
|----------|---------------|
| `deepseek-chat` | DeepSeek → `https://api.deepseek.com/v1` |
| `gpt-4o` | OpenAI → `https://api.openai.com/v1` |
| `claude-sonnet-4` | Anthropic → `https://api.anthropic.com/v1` |
| `glm-4` | Zhipu GLM → `https://open.bigmodel.cn/api/paas/v4` |
| `doubao-seed-2.0-pro` | ByteDance Doubao → `https://ark.cn-beijing.volces.com/api/v3` |
| `moonshot-v1` | Moonshot Kimi → `https://api.moonshot.cn/v1` |
| `qwen-max` | Alibaba Qwen → `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `llama3.1` | Local Ollama → `http://localhost:11434/v1` |

### Environment Variables (Quick Mode)

```bash
export DEEPSEEK_API_KEY="sk-your-key"
export OPENAI_API_KEY="sk-your-key"
export ANTHROPIC_API_KEY="sk-ant-your-key"
export GLM_API_KEY="your-key"
export DOUBAO_API_KEY="your-key"
export MOONSHOT_API_KEY="your-key"
export DASHSCOPE_API_KEY="your-key"
```

### Configuration File (`config/default.yaml`)

```yaml
systems:
  raft_kv:                          # Legacy: specific target systems
    project_path: "/path/to/project"
    benchmark_command: "./bench.sh"

models:                             # Legacy: static model config
  - name: "deepseek"
    provider: "openai_compatible"
    enabled: true
```

> **Note**: The `config/default.yaml` is retained for backward compatibility.
> In v0.5, the interactive CLI wizard is the primary configuration path.

---

## Extending SmartBench

### Adding a New Language

1. **Detection** — Add extension to `_EXTENSION_MAP` and manifest to `_MANIFEST_MAP` in `detector/scanner.py`
2. **Code Graph** — Add regex patterns to `_PATTERNS` in `graph/builder.py`
3. **Guidance** — Add language hints to `_language_specific_guidance()` in `prompts/factory.py`
4. **Diagnostics** — Create a `DiagnosticTool` subclass in `diagnostics/tools.py`

Example — adding Ruby support:

```python
# 1. scanner.py — already done: .rb extension + Gemfile manifest
# 2. builder.py _PATTERNS:
Language.RUBY: {
    "function": re.compile(r'def\s+(?P<name>\w+)', re.MULTILINE),
    "class": re.compile(r'class\s+(?P<name>\w+)', re.MULTILINE),
    "call": re.compile(r'(?P<name>\w+)\s*\(', re.MULTILINE),
},
# 3. factory.py _language_specific_guidance:
Language.RUBY: "Use ruby-prof / stackprof for profiling\n...",
# 4. tools.py — add RubyDiagnosticTool(DiagnosticTool): ...
```

### Adding a New LLM Provider

Add an entry to `PROVIDER_REGISTRY` in `cli.py`:

```python
PROVIDER_REGISTRY = {
    # ... existing providers ...
    "newprovider": {
        "base_url": "https://api.newprovider.com/v1",
        "patterns": ["newprovider-"],
        "display": "New Provider",
    },
}
```

---

## FAQ

### Q: Does SmartBench modify my code?
**No.** SmartBench only analyzes and suggests. It never writes to your project directory.

### Q: Do I need to reconfigure API keys every time?
**Yes, by design.** Keys are stored in memory only. When you close the terminal
and start a new `smartbench` session, you re-enter your keys. This ensures
keys are never accidentally persisted to disk.

### Q: What if my project uses multiple languages?
SmartBench detects the **primary** language by file count and lists secondary
languages. The code graph and diagnostics focus on the primary language.
Mixed-language projects get the `mixed` language tag.

### Q: Can I use a local LLM (Ollama, vLLM)?
Yes. Use a model name starting with `llama`, `mistral`, `qwen2`, `codellama`,
or `deepseek-r1` — SmartBench auto-routes to `http://localhost:11434/v1`.

### Q: What if my project has no README?
Phase 1 (deterministic scanning) still works perfectly. Phase 2 (LLM project
understanding) skips gracefully. The debate engine uses file content + graph
context instead.

### Q: How is the code graph built without compiling?
SmartBench uses regex-based heuristic parsing for speed and zero-dependency
operation. It captures ~85-90% of function/class definitions and call edges.
For production use, install `tree-sitter` for precise AST parsing:
```bash
pip install tree-sitter
```

---

## Changelog

### v0.5.0 (2026-06-13) — Universal Platform Refactor

- **New**: `detector/` — 14-language zero-LLM project fingerprinting
- **New**: `prompts/` — Dynamic PromptFactory, all hardcoded assumptions removed
- **New**: `graph/` — Code graph engine (12 languages, AST→graph→retrieval)
- **New**: `diagnostics/` — Pluggable tool registry (8 tools, language-routed)
- **Refactor**: `engine/debate.py` — Complete rewrite, zero Raft KV references
- **Refactor**: `cli.py` — 67KB→13KB, three-mode interactive wizard
- **UX**: Masked API key input with `*` echo and `****abcd` confirmation
- **UX**: Model-name-driven auto-config (8 providers)
- **Fix**: 9 bugs from comprehensive self-audit (I/O caching, precedence, type matching, language detection)

### v0.4 (2026-04-13)
- Diagnostic engine: crash, deadlock, memory leak, performance bottleneck detection
- GDB + flamegraph + Linux diagnostic tools integration

### v0.3 (2026-04-13)
- Multi-agent debate engine (Proposer/Critique/Judge)
- Code cache + performance regression analysis

### v0.2 (2026-04-10)
- Multi-model collaboration, weight engine, suggestion aggregation

### v0.1 (2026-04-08)
- Initial release: Raft KV benchmark + basic analysis

---

## License

MIT
