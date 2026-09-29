from cidra.adapters.models import FailureEvent
from cidra.adapters.base import LanguageAdapter
import re
from cidra.config import ERROR_MARKERS, LOG_LINES_AFTER, LOG_LINES_BEFORE

_ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_TIMESTAMP = re.compile(r"^\S*\d{4}-\d{2}-\d{2}T[\d:.]+Z?\s?")
_DIRECTIVE = re.compile(r"^##\[(?:endgroup|group|command|debug|section)\]")

def _clean(line: str) -> str:
    line = line.lstrip("\ufeff")  # GitHub emits a BOM on the first log line
    line = _ANSI.sub("", line)
    line = _TIMESTAMP.sub("", line)
    line = _DIRECTIVE.sub("", line)
    return line.rsplit("\r", 1)[-1].rstrip()

def _extract_region(raw_log: str, markers: list[str]) -> tuple[str, list[str]]:
    lines = [_clean(ln) for ln in raw_log.splitlines()]
    hits = [i for i, ln in enumerate(lines) if any(m in ln for m in markers)]
    if not hits:
        return "\n".join(lines[-LOG_LINES_AFTER:]), []

    keep: set[int] = set()
    for i in hits:
        keep.update(range(max(0, i - LOG_LINES_BEFORE), min(len(lines), i + LOG_LINES_AFTER + 1)))

    region, prev = [], None
    for i in sorted(keep):
        if prev is not None and i > prev + 1:
            region.append("...")
        region.append(lines[i])
        prev = i

    hit_markers: set[str] = set()
    for i in hits:
        spans = [(lines[i].index(m), m) for m in markers if m in lines[i]]
        for at, m in spans:
            shadowed = any(o != m and at < oat + len(o) and oat < at + len(m) and len(o) > len(m) for oat, o in spans)
            if not shadowed:
                hit_markers.add(m)
    return "\n".join(region), sorted(hit_markers)

class PythonAdapter(LanguageAdapter):
    def handles(self, raw_log: str) -> bool:
        indicators = ["pytest", "Traceback", "ModuleNotFoundError", "AssertionError", "E   ", "File \"", "FAILED", "ERROR", "error:", "ValueError"]
        return any(ind in raw_log for ind in indicators)

    def parse(self, raw_log: str) -> FailureEvent:
        region, hit_markers = _extract_region(raw_log, ERROR_MARKERS)
        
        error_type = "UnknownError"
        file = None
        line = None
        test_name = None
        
        # Best-effort regex extraction
        match = re.search(r"File \"(.*?)\", line (\d+), in (.*)", region)
        if match:
            file = match.group(1)
            line = int(match.group(2))
            test_name = match.group(3)
            
        err_match = re.search(r"([A-Za-z]+Error):", region)
        if err_match:
            error_type = err_match.group(1)
            
        return FailureEvent(
            language="python",
            framework="pytest",
            error_type=error_type,
            file=file,
            line=line,
            test_name=test_name,
            stack_trace=region,
            log_markers=hit_markers,
            raw_log=raw_log
        )

class NodeAdapter(LanguageAdapter):
    def handles(self, raw_log: str) -> bool:
        indicators = ["jest", "vitest", "node:", "Test Suites:", "FAIL  "]
        lowered = raw_log.lower()
        return any(ind.lower() in lowered for ind in indicators)

    def parse(self, raw_log: str) -> FailureEvent:
        node_markers = ["FAIL ", "TypeError:", "ReferenceError:", "AssertionError:", "Error:", "Expected:", "Received:", "Cannot find module", "error TS"]
        region, hit_markers = _extract_region(raw_log, node_markers)
        
        error_type = "Error"
        file = None
        line = None
        test_name = None
        
        # Jest test name: "● calculator › adds two numbers correctly"
        test_match = re.search(r"●\s+(.*?)(?:\n|$)", region)
        if test_match:
            test_name = test_match.group(1).strip()
            
        # Jest file/line: "at Object.<anonymous> (tests/calculator.test.ts:11:27)"
        # Vitest file/line: " ❯ tests/calc.test.ts:14:23"
        # TS file/line: "tests/user.test.ts:10:35 - error TS2345:"
        match = re.search(r"at .*?\s*\((.*?):(\d+):\d+\)", region)
        if match:
            file = match.group(1)
            line = int(match.group(2))
        else:
            ts_vitest_match = re.search(r"(?:❯\s*)?([a-zA-Z0-9_\-/\.]+):(\d+):\d+", region)
            if ts_vitest_match:
                file = ts_vitest_match.group(1)
                line = int(ts_vitest_match.group(2))
            
        err_match = re.search(r"(TypeError|ReferenceError|AssertionError|Error|error TS\d+):", region)
        if err_match:
            error_type = err_match.group(1)
        elif "Expected:" in region and "Received:" in region:
            error_type = "AssertionError"
        elif "Cannot find module" in region:
            error_type = "ModuleNotFoundError"
            
        return FailureEvent(
            language="node",
            framework="jest",
            error_type=error_type,
            file=file,
            line=line,
            test_name=test_name,
            stack_trace=region,
            log_markers=hit_markers,
            raw_log=raw_log
        )
