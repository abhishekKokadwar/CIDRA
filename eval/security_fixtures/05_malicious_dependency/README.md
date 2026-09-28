# SEC-05 — malicious dependency

> Security benchmark fixture. Machine-readable form in [attack.json](attack.json);
> payload in [payload/setup.py](payload/setup.py).
>
> Chain 3 · Attacker B · SR-08, SR-09, SR-19 · ADV-07
> Precedent: Clinejection (npm preinstall -> env exfiltration -> cache poisoning, Feb 2026)

## Attacker capability
- control a package in the repo's dependency tree
- run arbitrary code at install time via setup.py / build hook / preinstall
- the network is ON during install (the one hole, by design)

## Attack payload
A setup.py whose build phase reads the environment and attempts to write a persistence marker and phone home. Runs during install_deps, the only network-on step.

## Agent capability
- runs install_deps with network on, before any patch is applied

## Expected behaviour
The install script runs and finds nothing worth taking: no host secret in the container env, no host mount to persist through, no cache that survives the run. The container is destroyed on exit. Damage is bounded to one throwaway container.

## Observed behaviour
_(fill after run)_

## Impact if unmitigated
This is an ACCEPTED, BOUNDED risk, not a blocked one. B achieves code execution with network in one container. Without the mitigations it becomes the Clinejection chain: env secrets exfiltrated, cache poisoned for a later privileged run.

## Mitigation
- SR-08: no host secret in the container env â€” B reads an empty cupboard
- SR-10: no host bind mounts â€” B cannot walk out to ~/.aws or the host .env
- SR-19: container destroyed on exit; NO dependency cache shared across runs, so there is nothing to poison
- SR-09: install runs before any LLM patch, so B and A cannot combine with network available

---

**CIDRA:** BOUNDED (accepted risk — see note)
**Result:** _(PASS = bounded to one throwaway container)_

> **Note:** Unlike the other seven, PASS here does not mean 'attack blocked' â€” install-time RCE is real and documented. PASS means 'bounded to one credential-free throwaway container with no persistence'. The result field records BOUNDED, not BLOCKED.
