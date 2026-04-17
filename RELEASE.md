# Consilium v0.1.0-mvp — release checklist

Tracking against the Definition of Done in [MVP_PLAN.md §8](./MVP_PLAN.md). Not yet tagged.

- [ ] Demo video embedded in README showing all four scenes from MVP_PLAN §2.3 (happy, veto, soft-concern, audit)
- [ ] Red Team test set: 5/5 veto on known-bad, ≤1/10 false positive on benign
- [ ] Generalist test set: 5/5 concern on must-concern, ≤2/10 false concern on benign
- [ ] Citation parser tests pass: uncited concern → abstain; Generalist `veto` → protocol_violation
- [ ] Quorum engine enforces voter-class invariant (test + manual smoke)
- [ ] `consilium audit verify` command exists and produces a readable cryptographic proof across all three voter signatures
- [ ] Fresh-clone cold install completes in ≤15 minutes on Linux or macOS with Docker Desktop
- [ ] Every signed artefact in a deliberation verifies against its publishing agent's Vault transit key (five keys including `generalist`)
- [ ] The Speaker rejects tampered opinions (negative test documented)
- [ ] CI pipeline passes on `main`
- [ ] `v0.1.0-mvp` tag exists with attached release notes
- [ ] README, ARCHITECTURE, IMPLEMENTATION, MVP_PLAN, voting-architecture docs are consistent with shipped behaviour

## Release notes draft

_Populate on tag._

### What this is

### What you can do with it today

### What's explicitly out of scope for v0.1.0

See [MVP_PLAN.md §2.2](./MVP_PLAN.md) "Explicitly deferred to post-MVP".

### Verifying the demo yourself

```
git clone <repo>
cd consilium
docker compose -f dev/docker-compose.yml up -d
./dev/bootstrap.sh
cd examples/minimal_parliament && terraform init && terraform apply
consilium submit "Add a t3.small to dev-vpc"
```
