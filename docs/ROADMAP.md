# IMS roadmap

The v5.0 CLI has implemented inventory and authentication behavior; a separate Flask web-deployment proposal remains open in PR #3. This roadmap describes future work, not committed delivery dates.

## Completed correctness work

Current main persists successful-login audit entries, rejects non-finite numeric inputs, rejects inactive actors for protected operations, validates discrete-unit changes and item names, and disables unauthenticated CLI demo seeding. Eight focused regression tests cover these behaviors.

## Next correctness and recovery work

- Define exact money precision and failed-login logging.
- Add login-rate and session/recovery policies as the interface develops.
- Test concurrent writes and simultaneous first-admin creation.
- Provide verified SQLite backup creation and a restore workflow.
- Add schema versioning and migrations; preserve originals when upgrading.
- Define item archiving, audit formats and unique report filenames.

## Business requirements

Validate actual shop units, stock reconciliation and reporting needs. Design sales, returns, credit and payment records before presenting the CLI as a complete POS/accounting product. Business Automation is a separate application design that can build on these lessons.

## Deployment work

The web-deployment PR is a separate pending change. This documentation cleanup does not merge it or change Vercel production. Verify deployment and runtime access before marking that work complete.
