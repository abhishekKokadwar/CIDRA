from dataclasses import dataclass, field
from typing import Optional

@dataclass
class FailureEvent:
    """Normalized representation of a CI failure across any language/framework."""
    language: str              # e.g., "python", "node", "go"
    framework: str             # e.g., "pytest", "jest", "vitest", "go test"
    error_type: str            # e.g., "AssertionError", "TypeError"
    file: Optional[str] = None # Failing test file or source file if determinable
    line: Optional[int] = None # Line number of the failure
    test_name: Optional[str] = None # Name of the failing test
    stack_trace: str = ""      # The isolated raw stack trace / error region
    log_markers: list[str] = field(default_factory=list) # Found error markers
    raw_log: str = ""          # The complete raw CI log
    
    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "framework": self.framework,
            "error_type": self.error_type,
            "file": self.file,
            "line": self.line,
            "test_name": self.test_name,
            "stack_trace": self.stack_trace,
            "log_markers": self.log_markers,
            "raw_log": self.raw_log
        }
