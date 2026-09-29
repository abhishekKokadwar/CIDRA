import abc
from cidra.adapters.models import FailureEvent

class LanguageAdapter(abc.ABC):
    """Base interface for language-specific CI log parsers."""
    
    @abc.abstractmethod
    def handles(self, raw_log: str) -> bool:
        """Return True if this adapter recognizes the log format."""
        pass

    @abc.abstractmethod
    def parse(self, raw_log: str) -> FailureEvent:
        """Convert a raw CI log into a normalized FailureEvent."""
        pass
