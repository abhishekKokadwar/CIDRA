from cidra.adapters.dispatcher import dispatcher

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

def main():
    print("=== Testing NodeAdapter with Jest Log ===")
    
    # 1. Dispatcher should route it to NodeAdapter
    failure = dispatcher.parse_log(RAW_JEST_LOG)
    
    print(f"Language:  {failure.language}")
    print(f"Framework: {failure.framework}")
    print(f"ErrorType: {failure.error_type}")
    print(f"File:      {failure.file}")
    print(f"Line:      {failure.line}")
    print(f"Markers:   {failure.log_markers}")
    print("\n--- Stack Trace Region ---")
    print(failure.stack_trace)
    
    print("\n=== Testing Ingestion Compatibility ===")
    from cidra.nodes.ingest import isolate_error
    out = isolate_error({"raw_log": RAW_JEST_LOG})
    print(f"Ingested Error Region length: {len(out['error_region'])}")
    print(f"Ingested Markers: {out['log_markers']}")

if __name__ == "__main__":
    main()
