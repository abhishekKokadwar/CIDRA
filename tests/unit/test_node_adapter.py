"""The Node.js adapter parses a Jest failure log. Log parsing only: CIDRA does not install,
test or patch Node.js projects."""

from cidra.adapters.dispatcher import dispatcher
from cidra.nodes.ingest import isolate_error

RAW_JEST_LOG = """
FAIL  tests/calculator.test.ts
  calculator
    ✕ adds two numbers correctly (3 ms)

  ● calculator › adds two numbers correctly

    expect(received).toBe(expected) // Object.is equality

    Expected: 5
    Received: -1

       9 | describe('calculator', () => {
      10 |     it('adds two numbers correctly', () => {
    > 11 |         expect(add(2, 3)).toBe(5);
         |                           ^
      12 |     });
      13 | });

      at Object.<anonymous> (tests/calculator.test.ts:11:27)

Test Suites: 1 failed, 1 total
Tests:       1 failed, 1 total
Snapshots:   0 total
Time:        0.316 s
Ran all test suites.
"""


def test_jest_log_is_routed_to_the_node_adapter():
    failure = dispatcher.parse_log(RAW_JEST_LOG)
    assert (failure.language, failure.framework) == ("node", "jest")
    assert failure.error_type == "AssertionError"
    assert (failure.file, failure.line) == ("tests/calculator.test.ts", 11)


def test_jest_log_reaches_the_error_region():
    out = isolate_error({"raw_log": RAW_JEST_LOG})
    assert "expect(add(2, 3)).toBe(5)" in out["error_region"]
