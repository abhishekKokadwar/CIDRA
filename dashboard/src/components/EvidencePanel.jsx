import { ListChecks } from 'lucide-react';

// The report's evidence block (cidra/evidence.py), from the run's `evidence`:
// each test before and after the patch, the cost, and the command to rerun it.
const OUTCOME_COLOR = { passed: 'var(--color-success)', failed: 'var(--color-error)', error: 'var(--color-error)' };

export default function EvidencePanel({ evidence }) {
  if (!evidence) return null;
  const { tests = [], unchanged = {}, cost_usd: cost, price_source: priceSource, rerun_command: rerun } = evidence;
  const unchangedTotal = Object.values(unchanged).reduce((a, b) => a + b, 0);
  if (!tests.length && !unchangedTotal && cost == null && !rerun) return null;

  return (
    <section className="glass-panel" aria-label="Evidence" style={{ padding: '1.5rem', marginTop: '2rem' }}>
      <h3 style={{ fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <ListChecks size={16} color="var(--color-accent)" /> Evidence
      </h3>
      <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)', margin: '0.25rem 0 1rem' }}>
        Each test before and after the patch, as the sandbox recorded it.
      </p>

      {(tests.length > 0 || unchangedTotal > 0) && (
        <div style={{ width: '100%', overflowX: 'auto' }}>
          <table>
            <thead>
              <tr><th style={{ paddingLeft: 0 }}>Test</th><th>Before</th><th>After</th></tr>
            </thead>
            <tbody>
              {tests.map((t) => (
                <tr key={t.test}>
                  <td style={{ paddingLeft: 0, fontFamily: 'var(--font-code)', fontSize: '0.8rem' }}>
                    {t.test}
                    {t.note && (
                      <span style={{ marginLeft: '0.5rem', fontSize: '0.7rem', color: t.note === 'now failing' ? 'var(--color-error)' : 'var(--text-muted)' }}>
                        ({t.note})
                      </span>
                    )}
                  </td>
                  <td style={{ color: OUTCOME_COLOR[t.before] }}>{t.before}</td>
                  <td style={{ color: OUTCOME_COLOR[t.after] }}>{t.after}</td>
                </tr>
              ))}
              {unchangedTotal > 0 && (
                <tr>
                  <td style={{ paddingLeft: 0, color: 'var(--text-muted)' }}>{unchangedTotal} other tests, unchanged</td>
                  <td colSpan={2} style={{ color: 'var(--text-muted)' }}>
                    {Object.entries(unchanged).map(([o, n]) => `${n} ${o}`).join(', ')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {cost != null && (
        <p style={{ fontSize: '0.85rem', marginTop: '1rem' }}>
          Model cost: about <strong>${cost.toFixed(4)}</strong> at {priceSource}.
        </p>
      )}

      {rerun && (
        <div style={{ marginTop: '1rem' }}>
          <p style={{ fontSize: '0.85rem', marginBottom: '0.5rem' }}>
            Rerun this verification in your own sandbox (<code>fix.diff</code> is the fix&apos;s diff, e.g.{' '}
            <code>gh pr diff &lt;number&gt; &gt; fix.diff</code>):
          </p>
          <pre style={{ fontFamily: 'var(--font-code)', fontSize: '0.75rem', whiteSpace: 'pre-wrap', wordBreak: 'break-all', background: 'var(--bg-dark)', border: '1px solid var(--border-light)', borderRadius: '6px', padding: '0.75rem' }}>
            {rerun}
          </pre>
        </div>
      )}
    </section>
  );
}
