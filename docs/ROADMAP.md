# IMS roadmap

The v5.0 CLI manages inventory with local authentication. The [Flask demo](../README.md#browser-demo) uses a browser-local workspace with fictional data.

## Completed correctness work

Current main persists successful-login audit entries, rejects non-finite numeric inputs, rejects inactive actors for protected operations, validates discrete-unit changes and item names, and disables unauthenticated CLI demo seeding. Eight focused regression tests cover these behaviors.

## Next correctness and recovery work

- Define exact money precision and failed-login logging.
- Add login-rate and session/recovery policies as the interface develops.
- Test concurrent writes and simultaneous first-admin creation.
- Provide verified SQLite backup creation and a restore workflow.
- Add schema versioning and migrations; preserve originals when upgrading.
- Define item archiving and audit formats.

## Business requirements

Validate actual shop units, stock reconciliation and reporting needs. Design sales, returns, credit and payment records before presenting the CLI as a complete POS/accounting product. Business Automation is a separate application design that can build on these lessons.

## Deployment work

For a shared web edition, define authenticated staff access, durable storage and
backup recovery before a pilot. Verify the deployment and run the store workflow
against the proposed database.
