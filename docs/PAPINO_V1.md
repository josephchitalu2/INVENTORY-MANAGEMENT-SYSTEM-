# PAPINO Investments Limited — POS & IMS v1

Offline, single-PC web application. The cashier uses Firefox at
http://127.0.0.1:8080 while the Python/Waitress server runs on the same PC.
This is separate from the Vercel portfolio demo. Internet is needed to install
Python packages initially, not for normal trading.

## Start on your EndeavourOS laptop

1. Stop any older IMS server. Download and extract `PAPINO_POS_IMS_v1.zip` into a new folder.
2. Open a terminal inside the extracted `PAPINO_POS_IMS_v1` folder.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-store.txt
python store_setup.py
python store_app.py
```

Open **http://127.0.0.1:8080**. Do not open HTML template files directly.
If an owner account already exists, skip `store_setup.py` and use that account.
To start again later: activate `.venv`, then run `python store_app.py`.
Keep the terminal running; closing it stops the app.
On Windows use `.venv\Scripts\activate` in Command Prompt instead of `source`.

Existing local-store records are retained in `~/.local/share/chitalu-ims/`,
independently of the extracted code folder. Updating code does not reset them.
**Download a database backup before updating.** The Vercel browser-demo data
is separate and is not automatically migrated.

For a completely isolated trial, set a separate data directory before BOTH setup and startup:

```bash
export IMS_DATA_DIR="$HOME/papino-training-data"
python store_setup.py
python store_app.py
```

When moving to real trading, stop this process, open a fresh terminal without
that training variable, and start the normal store. Do not mix trial transactions
with live records. The default live store remains empty until you enter stock.

## Prepare the shop

- Sign in as admin. Under Account & staff, create a manager account for Dad
  and separate staff accounts for the regular and relief cashiers. No default passwords.
- Under Stock, select **Prepare PAPINO catalog**. It creates missing products only,
  with zero opening stock and zero cost price. It never invents physical quantities.
- In the inventory editor, set actual cost prices, reorder levels and opening stock.
  Add deliveries using stock-in with a reason. A stock purchase paid from the till
  also needs its separate expense entry; receiving goods alone does not remove cash.
- Ensure the PC clock and the cameras match. POS events use Africa/Lusaka (+02:00).
- Check receipt printing with the actual printer. Register/drawer connectivity is
  not included; no hardware compatibility is assumed.

| Product | Unit | Selling price |
| --- | --- | ---: |
| Fish | kg | K68 |
| Sausage | kg | K100 |
| Fresh kapenta | pack | K30 |
| Buka fish | kg | K90 |
| Chicken pieces | kg | K120 |
| Game meat (bundle) | whole pack = one bundle | K350 |

## Daily trading

1. Cashier opens a named shift, entering the physically counted opening cash.
   Normal float is K500; differences from K500 or the prior closing float need an explanation.
   Only one till shift may be active at a time.
2. Add products to the basket. Kilograms support three decimal places; other units
   require whole quantities. Barcode mapping is optional and manager-controlled.
3. Allocate payment across Cash, Zanaco and/or Airtel. Enter cash received separately
   to calculate change. The amount allocated to cash is net cash retained, not the tendered note.
4. Electronic payments require references. They remain cashier declarations until
   Dad reconciles against the actual company line or terminal. Customer screenshots
   do not become automatic account confirmation.
5. If money remains owed, provide debtor name/contact, recipient, due date and Dad's
   declared authorization. Later repayments settle this receipt without another stock deduction.
   Dad can verify the credit authorization from Credit & receipts.
6. Receipts can be opened and reprinted. Clicking Pay again with the same pending
   request cannot create a second sale. Unfinished baskets are saved in that cashier's browser.

**Cash formula:** opening cash + cash sales/repayments + cash added/returned
− cash refunds − expenses − owner deposits.
Card/Airtel amounts never count as physical till cash.

## Expenses and cash collected

- Record payee, category, amount and purpose for cash expenses.
- Lunch and plastics are the agreed routine categories. Other expenses require
  a recorded owner-approval declaration. Software does not verify phone calls.
- For **Cash collected → company Airtel via agent**, enter Dad's request, the
  agent name and reference. The amount leaves the till once. Dad confirms actual
  receipt in Owner review; this does not deduct cash again. No transfer fee is assumed.
- A failed deposit remains unconfirmed. An owner can record cash returned with
  a reason/reference linked to the failed handover, or complete the deposit later.
  Retain that explanation in the event trail; do not silently delete either entry.

## Closing and cameras

The cash counter includes K500 and K200 notes as well as smaller denominations,
checked against the [Bank of Zambia currency overview](https://www.boz.zm/currency/overview).
Start closing pauses checkout. Count denominations before the expected balance
is shown to a cashier account. The first count and timestamps are preserved.
Reasoned recounts append new records rather than overwriting the first count.

After the count, only closing owner deposits may remove till cash. Finish closing
by entering actual remaining cash; it must equal the latest count minus subsequent
closing deposits. Retain K500 where physically possible. A shortage, surplus or
non-K500 float requires an explanation. The software never fills a gap automatically.

Closed shifts cannot accept new sales or ordinary ledger edits. The next cashier
opens their own shift. Dad's review is separate from cashier closing and requires
owner-deposit, expense, electronic-payment and credit-authorization reviews first.
Review tables include first-count difference, method totals and till movement totals.
Download the full event ledger as CSV for archived reporting.

## Ma dawari, losses and refunds

A manager can reclassify safe-to-eat downgraded stock into a distinct ma dawari
product at an approved price. The original stock decreases and discounted stock
increases together. Subsequent sales belong to the shop. There is no automatic
69% price reduction. Disposal, staff use and gifts have distinct reasoned withdrawals.

Managers can reverse a **whole sale**, recording reasons and exact refunds of the
amount actually received, including later repayments. Unpaid credit is cancelled.
Choose explicitly whether all goods can safely be restocked; default is no restock.
The original receipt remains marked reversed. **Partial returns are not supported in v1.**
For a partial return or a complex dispute, preserve the original records and have
Dad supervise the correction instead of improvising an unrelated till expense.

Log card/Airtel exceptions with references and follow-up details. The exception
log itself never deducts stock. If Dad releases goods while payment is disputed,
record an authorized credit sale tied to the same reference. Owner resolution notes
are append-only and link the eventual outcome; bank or mobile money reversals
are not executed by this app.

## Backups, power and limits

The database and secret key stay on the PC. Automatic consistent SQLite backups
run on startup and before trading writes; newest 30 are retained locally.
Admin can download a full backup. Copy one to another drive daily and after closing.
These contain store information and password hashes; keep them private.

Stop the server before recovery:

```bash
python store_restore.py /path/to/ims-store-backup.sqlite3
```

Recovery validates the file, retains a pre-restore copy, and clears web sessions.
Restart and sign in using credentials from the restored backup.

SQLite transactions prevent partial checkouts; duplicate-request checks protect
sales and payments. A laptop battery/UPS still matters: sudden disk/hardware failure
can lose data, and a generator does not keep a desktop alive during changeover.
After interruption, verify the existing receipt/external payment before retrying.
Never repeat an external card/mobile charge merely because a receipt did not print.

This is a one-PC, one-till system, not an internet/LAN deployment. No direct Zanaco,
Airtel, scale, register, cash-drawer or camera integration is included. Browser
printing is the receipt path. No fiscal-device/tax compliance claim is made.
It records business events; it does not prove physical money changed hands.
An OS administrator can alter local files: use owner-controlled OS credentials,
restricted cashier OS access, and protect backup copies.

## Acceptance run before live trading

Use training data and verify:

- Owner and cashier login/permissions; create one separate relief cashier.
- Stock receipt, a 0.75 kg fish sale for K51, split payment, receipt print/reprint.
- Credit issue, partial repayment, outstanding balance and owner verification.
- Expense approval declaration and owner deposit/receipt confirmation.
- Ma dawari reclassification/sale and separate disposal.
- Blind closing, reasoned recount, closing deposit, actual K500 float and owner review.
- Full-sale reversal with and without restocking.
- Server restart, pending basket recovery and duplicate checkout protection.
- Download a backup and restore into an isolated training directory.
- Compare the whole practice shift with manual calculations and camera timestamps.

Automated verification: 27 Python tests cover persistence, permissions, CSRF,
session revocation, split/weighted sales, atomic failure, concurrent duplicate checkout,
credit repayments, reclassification, refunds, blind closing, recounts and owner reviews.
A DOM integration pass against the running server checked login, catalog, stock,
shift opening, weighted checkout, receipt, all tabs and closing count with no script
errors. Full graphical-browser visual verification and actual store hardware testing
remain pending; the browser download was unavailable in the build environment.
