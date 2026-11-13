# IMS CLI operator guide

This guide covers the Python CLI on `main`. See the [README](../README.md) for
installation and the [technical guide](TECHNICAL.md) for permissions and limits.

## Practise in a separate database

From the folder containing `ims.py`:

```bash
python3 ims.py --db ./sandbox/inventory.db
```

Create an administrator when prompted, then sign in. Use **13 · Seed demo inventory**
to load fictional products, or use **3 · Add item** and enter an opening quantity.
On later runs, pass the same database path to get the same data. The default
database is `data/inventory.db` beside the script.

## Record stock and review the result

| Goal | Menu | What to enter or expect |
| --- | --- | --- |
| Find an item ID | **1** View or **2** Search | Use the ID shown in the inventory list. |
| Receive a delivery | **4** Stock in | Enter its ID, a positive quantity in its unit, and an optional note. |
| Remove stock | **5** Stock out | Enter the ID and amount. A quantity above available stock is rejected. |
| Change an item detail | **6** Update item | Enter only the fields that changed. Correct a stock count with a movement and a note. |
| Review stock or movements | **7**, **8**, **9** | Inspect low stock or export inventory and movement CSVs. |

For example, create a practice item with 5 kg, record 2 kg in, then 0.5 kg out.
The current quantity should be 6.5 kg. Pack, bottle and piece items require whole
units. Movement value uses cost price; it is not a record of sales revenue.

## Locate your data

With the practice command, look under `sandbox/` for `inventory.db` and under
`sandbox/reports/` for CSV exports. Stop the app before copying its SQLite file.
The CLI has no built-in backup/restore workflow. CSVs help you read the records;
they cannot restore the database.

Before using an existing database, check the path. An unexpected first-run
administrator prompt can mean you opened a new file. Exit and confirm the
location of the original database before continuing.
