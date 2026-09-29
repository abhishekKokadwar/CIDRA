from typing import List
from cidra.adapters.models import FailureEvent
from cidra.adapters.base import LanguageAdapter
from cidra.adapters.implementations import PythonAdapter, NodeAdapter

class AdapterDispatcher:
    def __init__(self):
        self.adapters: List[LanguageAdapter] = [
            PythonAdapter(),
            NodeAdapter(),
            # GoAdapter(), # Can be added later
        ]

    def parse_log(self, raw_log: str) -> FailureEvent:
        """Finds the appropriate adapter and normalizes the log."""
        for adapter in self.adapters:
            if adapter.handles(raw_log):
                return adapter.parse(raw_log)
                
        # Fallback if no specific language is detected
        return FailureEvent(
            language="unknown",
            framework="unknown",
            error_type="UnknownError",
            raw_log=raw_log
        )

# Global singleton for easy import
dispatcher = AdapterDispatcher()
