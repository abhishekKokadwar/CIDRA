// The Run Explorer shows the report's evidence block.
// A test's [ID] ties it to docs/requirements.yml (scripts/check_requirements.py).
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import EvidencePanel from '../components/EvidencePanel';

afterEach(cleanup);

const EVIDENCE = {
  tests: [
    { test: 'tests.test_calc::test_add', before: 'failed', after: 'passed', note: 'target' },
    { test: 'tests.test_calc::test_sub', before: 'passed', after: 'failed', note: 'now failing' },
  ],
  unchanged: { passed: 4, skipped: 1 },
  cost_usd: 0.006,
  price_source: 'list price',
  rerun_command: "cidra verify --sha abc123 --patch fix.diff --install 'pip install .' --test 'pytest -q 2>&1'",
};

describe('evidence', () => {
  it('[UI-EVIDENCE] shows each test before and after, the cost and the rerun command', () => {
    render(<EvidencePanel evidence={EVIDENCE} />);
    const rows = screen.getAllByRole('row').map((r) => r.textContent);
    expect(rows).toContain('tests.test_calc::test_add(target)failedpassed');
    expect(rows).toContain('tests.test_calc::test_sub(now failing)passedfailed');
    expect(screen.getByText('5 other tests, unchanged')).toBeTruthy();
    expect(screen.getByText('4 passed, 1 skipped')).toBeTruthy();
    expect(screen.getByText('$0.0060')).toBeTruthy();
    expect(screen.getByText(EVIDENCE.rerun_command)).toBeTruthy();
  });

  it('[UI-EVIDENCE] shows nothing for a run that recorded none', () => {
    const { container } = render(<EvidencePanel evidence={{ tests: [], unchanged: {}, cost_usd: null, rerun_command: null }} />);
    expect(container.innerHTML).toBe('');
  });
});
