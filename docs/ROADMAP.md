# IMS roadmap

The current code remains the supplied v5.0 prototype. This roadmap describes proposed future work, not implemented features or committed delivery dates.

## First: correctness and access controls

- Commit successful-login audit entries and define failed-login logging.
- Reject NaN/infinity for all numeric inputs and define money precision.
- Recheck account activity during service operations.
- Validate unit changes against current quantity and reject empty renamed items.
- Replace unauthenticated command-line demo seeding with an explicitly authorised workflow.
- Add regression tests for these issues and concurrent first-admin creation.

## Next: recovery and data evolution

- Provide consistent SQLite backup creation with verification and a tested restore workflow.
- Add explicit schema versioning and migration tooling. v4 and v5 schemas are not automatically compatible.
- Add item archiving without losing historical movements.
- Avoid report filename collisions and define an audit value format.

## Later: business requirements

- Validate real shop units, supplier fields, stock reconciliation and reporting needs with the owner.
- Consider POS/sales integration only after designing sales, returns and accounting records.
- Evaluate a graphical interface and multi-user operation after measuring workflow needs.

Any claim of enterprise or production readiness needs deployment evidence, recovery tests, access-control testing and operational support. The current README intentionally makes no such claim.
