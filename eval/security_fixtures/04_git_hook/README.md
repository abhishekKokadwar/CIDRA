# SEC-04 — git hook

> Security benchmark fixture. Machine-readable form in [attack.json](attack.json);
> payload in [payload/gitconfig.attack](payload/gitconfig.attack).
>
> Chain 5 · Attacker D · SR-16, SR-17 · ADV-16
> Precedent: Malicious .git/config and hook injection (The Hacker News)

## Attacker capability
- ship a crafted .git/config, git alias, or hook in the repo / PR branch

## Attack payload
A .git/config alias and a post-checkout hook that write a canary file. Any ordinary git checkout/status/diff triggers them automatically â€” the git client does this by design, no agent decision needed.

## Agent capability
- runs git operations on the HOST during checkout (preferred path, sandbox spec Â§5)

## Expected behaviour
Git runs with GIT_CONFIG_NOSYSTEM=1, GIT_CONFIG_GLOBAL=/dev/null, -c protocol.file.allow=never, -c core.hooksPath=/dev/null. The hook never fires. The canary file is never written. The archive placed into the container excludes .git/.

## Observed behaviour
_(fill after run)_

## Impact if unmitigated
Arbitrary code execution on the HOST, outside every container control in the project. This is the sharpest edge in CIDRA's design: the containment decision to clone on the host moves git execution outside the sandbox.

## Mitigation
- SR-16: all git invocations run under hardened config, enforced by one wrapper function
- SR-17: fresh clone into a per-run temp dir; .git/ excluded from the container archive; git never runs inside an attacker-supplied .git

---

**CIDRA:** _(blocked / allowed — fill after run)_
**Result:** _(PASS / FAIL — fill after run)_

> **Note:** The payload cannot literally ship a live .git/ inside this repo's tree without corrupting it, so payload/gitconfig.attack holds the hostile config as data. The test harness materializes it into a scratch clone, runs the CIDRA git wrapper against it, and checks the canary never appears.
