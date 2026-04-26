"""Security guard: untrusted content wrapping and injection detection.

Per plan.md §8.1:
- Wrap external content in <external_content> tags with trust level
- Detect common injection patterns
- Integrate with circuit breaker for escalation
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = ["SecurityLevel", "Guard", "ExternalContent"]


class SecurityLevel(str, Enum):
    """Trust level for external content."""

    UNTRUSTED = "untrusted"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ExternalContent:
    """Wrapped external content with metadata."""

    source: str
    trust_level: SecurityLevel
    content: str
    injection_risk: float = 0.0  # 0.0-1.0
    risks_detected: list[str] = None

    def __post_init__(self):
        if self.risks_detected is None:
            self.risks_detected = []

    def to_xml(self) -> str:
        """Serialize to XML-like format for LLM context."""
        risks_str = "; ".join(self.risks_detected) if self.risks_detected else "none"
        return f"""<external_content source="{self._escape_xml(self.source)}" trust="{self.trust_level.value}" injection_risk="{self.injection_risk:.2f}" risks="{self._escape_xml(risks_str)}">
{self.content}
</external_content>"""

    @staticmethod
    def _escape_xml(text: str) -> str:
        """Minimal XML escaping."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )


class Guard:
    """Security guard for untrusted content."""

    # Injection patterns (regex)
    INJECTION_PATTERNS = {
        "prompt_injection": r"(?i)(ignore.*instruction|forget.*prompt|system.*override|jailbreak|new.*instruction|from now on|you are now|pretend|act as)",
        "sql_injection": r"(?i)(union|select|insert|update|delete|drop|exec|script)",
        "xss": r"(?i)(<script|javascript:|onerror|onload|<iframe|<object)",
        "path_traversal": r"(\.\./|\.\.\\|/etc/|C:\\)",
        "command_injection": r"(?i)(;|\||&|`|\$\(|sh\s+-c)",
    }

    def __init__(self, circuit_breaker: Any = None):
        """Initialize guard.

        Args:
            circuit_breaker: Optional CircuitBreaker for escalation on high-risk content
        """
        self.circuit_breaker = circuit_breaker

    def wrap_external(
        self,
        content: str,
        source: str,
        trust_level: SecurityLevel = SecurityLevel.UNTRUSTED,
    ) -> ExternalContent:
        """Wrap external content and analyze for injection risks."""
        risks = []
        max_risk = 0.0

        for pattern_name, pattern in self.INJECTION_PATTERNS.items():
            if re.search(pattern, content):
                risks.append(pattern_name)
                # Risk scoring: each pattern hit adds 0.2
                max_risk += 0.2

        max_risk = min(1.0, max_risk)

        wrapped = ExternalContent(
            source=source,
            trust_level=trust_level,
            content=content,
            injection_risk=max_risk,
            risks_detected=risks,
        )

        # Escalate to circuit breaker if risk is high
        if self.circuit_breaker and max_risk > 0.7:
            self.circuit_breaker.trip(reason=f"High injection risk ({max_risk:.2f}) from {source}")

        return wrapped

    def is_safe(self, wrapped: ExternalContent, threshold: float = 0.5) -> bool:
        """Check if content is safe based on injection risk."""
        return wrapped.injection_risk < threshold

    def sanitize(self, text: str) -> str:
        """Basic sanitization: remove script tags and suspicious patterns."""
        # Remove script tags
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.IGNORECASE | re.DOTALL)

        # Remove event handlers
        text = re.sub(r'\s*on\w+\s*=\s*["\'][^"\']*["\']', "", text)

        # Remove javascript: protocol
        text = re.sub(r"javascript:", "", text, flags=re.IGNORECASE)

        return text

    def get_risk_summary(self, wrapped: ExternalContent) -> dict[str, Any]:
        """Get structured risk analysis."""
        return {
            "source": wrapped.source,
            "trust_level": wrapped.trust_level.value,
            "injection_risk": wrapped.injection_risk,
            "risks_detected": wrapped.risks_detected,
            "is_safe": self.is_safe(wrapped),
            "recommended_action": self._recommend_action(wrapped),
        }

    @staticmethod
    def _recommend_action(wrapped: ExternalContent) -> str:
        """Recommend action based on risk level."""
        risk = wrapped.injection_risk
        if risk < 0.2:
            return "allow"
        elif risk < 0.5:
            return "allow_with_monitoring"
        elif risk < 0.7:
            return "sanitize_and_allow"
        else:
            return "reject"
