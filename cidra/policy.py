"""Granular Enterprise Policy Engine (cidra.policy.yml).

Allows security and platform teams to declaratively define:
1. auto_remediate: categories permitted for autonomous repair.
2. require_human_approval: categories and path patterns requiring explicit human gate.
3. strict_refusal: categories strictly forbidden from auto-repair (fail-closed).
4. containment_limits: blast-radius constraints on lines, files, and deletions.
"""

from __future__ import annotations

import fnmatch
import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

import yaml

log = logging.getLogger("cidra.policy")


class PolicyDecision(str, Enum):
    AUTO_REMEDIATE = "auto_remediate"
    REQUIRE_HUMAN_APPROVAL = "require_human_approval"
    STRICT_REFUSAL = "strict_refusal"


# Normalized category aliases to map between YAML configuration and CIDRA internal categories
_CATEGORY_ALIASES: dict[str, str] = {
    # Missing dependency
    "missing_dependency": "missing_dependency",
    "missing_dependencies": "missing_dependency",
    "dependency": "missing_dependency",
    "dependencies": "missing_dependency",
    "missing_package": "missing_dependency",
    # Environment variable / config
    "env_var_missing": "env_config_error",
    "missing_env_var": "env_config_error",
    "env_config_error": "env_config_error",
    "env_error": "env_config_error",
    "environment": "env_config_error",
    # Assertion error / drift
    "simple_assertion": "assertion_error",
    "assertion_error": "assertion_error",
    "test_assertion_drift": "assertion_error",
    "assertion": "assertion_error",
    # Flaky tests
    "flaky_tests": "flaky_test",
    "flaky_test": "flaky_test",
    "flakiness": "flaky_test",
    # Timeout
    "timeout_failures": "timeout",
    "timeout": "timeout",
    # Business logic / unknown
    "core_business_logic": "unknown",
    "business_logic": "unknown",
    "unknown": "unknown",
    # Lint / style
    "lint_style": "lint_error",
    "lint_error": "lint_error",
    "formatting": "lint_error",
}


def normalize_category(name: str) -> str:
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    return _CATEGORY_ALIASES.get(key, key)


@dataclass
class ContainmentLimits:
    max_changed_files: int = 5
    max_changed_lines: int = 100
    allow_file_deletion: bool = False
    allow_new_files: bool = True


@dataclass
class PolicyRule:
    auto_remediate: list[str] = field(default_factory=lambda: [
        "missing_dependency",
        "env_config_error",
        "assertion_error",
    ])
    require_human_approval_categories: list[str] = field(default_factory=lambda: [
        "unknown",
    ])
    require_human_approval_paths: list[str] = field(default_factory=lambda: [
        "src/auth/**",
        "auth/**",
        "migrations/**",
        "db/migrations/**",
        "payments/**",
        "**/*.sql",
    ])
    strict_refusal_categories: list[str] = field(default_factory=lambda: [
        "flaky_test",
        "timeout",
        "security_violation",
    ])
    forbidden_paths: list[str] = field(default_factory=lambda: [
        ".github/**",
        ".cidra/**",
        "AGENTS.md",
        "CLAUDE.md",
        "**/*.pem",
        "**/*.key",
        "**/*.id_rsa",
    ])
    containment: ContainmentLimits = field(default_factory=ContainmentLimits)


def _match_path(pattern: str, file_path: str) -> bool:
    """Case-insensitive glob matcher supporting ** wildcards."""
    norm_pattern = pattern.replace("\\", "/").strip().lower()
    norm_path = file_path.replace("\\", "/").strip().lower()

    if norm_pattern.endswith("/**"):
        prefix = norm_pattern[:-3]
        if norm_path.startswith(prefix) or norm_path == prefix.rstrip("/"):
            return True

    return fnmatch.fnmatch(norm_path, norm_pattern)


class PolicyEngine:
    def __init__(
        self,
        rule: Optional[PolicyRule] = None,
        policy_source: str = "default",
        policy_sha256: str = "default_enterprise_policy"
    ) -> None:
        self.rule = rule or PolicyRule()
        self.policy_source = policy_source
        self.policy_sha256 = policy_sha256

    def evaluate_category(self, category: Optional[str]) -> tuple[PolicyDecision, str]:
        """Evaluates whether an identified failure category is permitted for auto-repair."""
        if not category:
            return PolicyDecision.REQUIRE_HUMAN_APPROVAL, "Failure category was not determined"

        norm = normalize_category(category)

        # 1. Strict Refusal takes absolute priority
        for strict in self.rule.strict_refusal_categories:
            if norm == normalize_category(strict):
                return (
                    PolicyDecision.STRICT_REFUSAL,
                    f"Category '{category}' is designated for strict refusal by policy"
                )

        # 2. Require Human Approval takes second priority
        for approval in self.rule.require_human_approval_categories:
            if norm == normalize_category(approval):
                return (
                    PolicyDecision.REQUIRE_HUMAN_APPROVAL,
                    f"Category '{category}' requires human approval before applying changes"
                )

        # 3. Explicitly allowed categories
        for allowed in self.rule.auto_remediate:
            if norm == normalize_category(allowed):
                return PolicyDecision.AUTO_REMEDIATE, f"Category '{category}' is approved for autonomous repair"

        # Default fallback: unknown categories require human review
        return (
            PolicyDecision.REQUIRE_HUMAN_APPROVAL,
            f"Category '{category}' is not listed in auto_remediate allowlist"
        )

    def evaluate_diff(self, diff: str) -> tuple[PolicyDecision, list[str]]:
        """Evaluates a unified diff against path boundaries and containment limits."""
        reasons: list[str] = []
        requires_human = False

        if not diff or not diff.strip():
            return PolicyDecision.AUTO_REMEDIATE, ["Diff is empty"]

        # Parse files from unified diff
        changed_files: list[str] = []
        added_lines = 0
        removed_lines = 0
        deletions: list[str] = []

        cur_file: Optional[str] = None
        cur_old_path: Optional[str] = None
        for line in diff.splitlines():
            if line.startswith("--- "):
                raw_path = line[4:].strip()
                if raw_path != "/dev/null":
                    path = raw_path
                    for prefix in ("a/", "b/"):
                        if path.startswith(prefix):
                            path = path[len(prefix):]
                    cur_old_path = path
            elif line.startswith("+++ "):
                raw_path = line[4:].strip()
                if raw_path == "/dev/null":
                    if cur_old_path:
                        deletions.append(cur_old_path)
                        if cur_old_path not in changed_files:
                            changed_files.append(cur_old_path)
                else:
                    path = raw_path
                    for prefix in ("b/", "a/"):
                        if path.startswith(prefix):
                            path = path[len(prefix):]
                    cur_file = path
                    if path not in changed_files:
                        changed_files.append(path)
            elif line.startswith("+") and not line.startswith("+++"):
                added_lines += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed_lines += 1

        total_changed_lines = added_lines + removed_lines

        # Check containment: max files changed
        if len(changed_files) > self.rule.containment.max_changed_files:
            reasons.append(
                f"Patch modified {len(changed_files)} files (maximum permitted: {self.rule.containment.max_changed_files})"
            )
            return PolicyDecision.STRICT_REFUSAL, reasons

        # Check containment: max lines changed
        if total_changed_lines > self.rule.containment.max_changed_lines:
            reasons.append(
                f"Patch modified {total_changed_lines} lines (maximum permitted: {self.rule.containment.max_changed_lines})"
            )
            return PolicyDecision.STRICT_REFUSAL, reasons

        # Check file deletions
        if deletions and not self.rule.containment.allow_file_deletion:
            reasons.append(
                f"Patch deleted files {deletions}, which violates allow_file_deletion=False"
            )
            return PolicyDecision.STRICT_REFUSAL, reasons

        # Check path boundaries
        for fpath in changed_files:
            # Check forbidden paths
            for forbidden in self.rule.forbidden_paths:
                if _match_path(forbidden, fpath):
                    reasons.append(
                        f"File '{fpath}' matches forbidden path pattern '{forbidden}'"
                    )
                    return PolicyDecision.STRICT_REFUSAL, reasons

            # Check human-approval required paths
            for sensitive in self.rule.require_human_approval_paths:
                if _match_path(sensitive, fpath):
                    requires_human = True
                    reasons.append(
                        f"File '{fpath}' matches sensitive path pattern '{sensitive}'"
                    )

        if requires_human:
            return PolicyDecision.REQUIRE_HUMAN_APPROVAL, reasons

        return PolicyDecision.AUTO_REMEDIATE, ["Patch satisfies all policy safety boundaries"]

    @classmethod
    def load_from_dict(cls, data: dict, source_name: str = "dict", sha256_hash: str = "") -> PolicyEngine:
        rule = PolicyRule()
        pol = data.get("policy", data)

        if "auto_remediate" in pol and isinstance(pol["auto_remediate"], list):
            rule.auto_remediate = [str(item) for item in pol["auto_remediate"]]

        if "strict_refusal" in pol and isinstance(pol["strict_refusal"], list):
            rule.strict_refusal_categories = [str(item) for item in pol["strict_refusal"]]

        if "require_human_approval" in pol and isinstance(pol["require_human_approval"], list):
            cats: list[str] = []
            paths: list[str] = []
            for item in pol["require_human_approval"]:
                if isinstance(item, dict) and "path" in item:
                    paths.append(str(item["path"]))
                elif isinstance(item, str):
                    if item.startswith("path:") or "/" in item or "*" in item:
                        clean = item.removeprefix("path:").strip()
                        paths.append(clean)
                    else:
                        cats.append(item)
            rule.require_human_approval_categories = cats
            rule.require_human_approval_paths = paths

        if "forbidden_paths" in pol and isinstance(pol["forbidden_paths"], list):
            rule.forbidden_paths = [str(item) for item in pol["forbidden_paths"]]

        if "containment_limits" in pol and isinstance(pol["containment_limits"], dict):
            cl = pol["containment_limits"]
            rule.containment = ContainmentLimits(
                max_changed_files=int(cl.get("max_changed_files", rule.containment.max_changed_files)),
                max_changed_lines=int(cl.get("max_changed_lines", rule.containment.max_changed_lines)),
                allow_file_deletion=bool(cl.get("allow_file_deletion", rule.containment.allow_file_deletion)),
                allow_new_files=bool(cl.get("allow_new_files", rule.containment.allow_new_files)),
            )

        return cls(rule=rule, policy_source=source_name, policy_sha256=sha256_hash or "custom_policy")

    @classmethod
    def find_and_load(cls, search_dir: Optional[Union[str, Path]] = None) -> PolicyEngine:
        """Looks for cidra.policy.yml or .cidra/policy.yml starting in search_dir or cwd."""
        base = Path(search_dir) if search_dir else Path.cwd()
        candidate_paths = [
            base / "cidra.policy.yml",
            base / "cidra.policy.yaml",
            base / ".cidra" / "policy.yml",
            base / ".cidra" / "policy.yaml",
        ]

        for p in candidate_paths:
            if p.is_file():
                try:
                    content = p.read_text(encoding="utf-8")
                    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    parsed = yaml.safe_load(content) or {}
                    log.info("Loaded enterprise policy from %s (SHA-256: %s)", p, sha[:12])
                    return cls.load_from_dict(parsed, source_name=str(p), sha256_hash=sha)
                except Exception as err:
                    log.error("Failed to parse policy file %s: %s (falling back to default)", p, err)

        log.debug("No cidra.policy.yml found in %s; using enterprise defaults", base)
        return cls()
