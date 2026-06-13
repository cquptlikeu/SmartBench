"""Project detector — fingerprint a codebase without any LLM calls."""

from smartbench.detector.fingerprint import ProjectFingerprint, Language, Framework, ProjectType
from smartbench.detector.scanner import ProjectScanner

__all__ = ["ProjectFingerprint", "Language", "Framework", "ProjectType", "ProjectScanner"]
