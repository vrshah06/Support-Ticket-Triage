SUPPORT TICKET TRIAGE: DATA

tickets.csv contains 300 support tickets, one per row.

Columns
  id            Ticket number, for example T-0001
  received_at   When the ticket arrived
  customer      Customer name
  subject       Subject line
  body          Ticket text (can run over several lines)

The file is UTF-8 and uses standard CSV quoting.

Labels
  Categories: Billing, Technical, Account, Shipping, Other
  Priorities: Low, Medium, High, Urgent

Output
Produce a file named results.csv with one row per ticket and these columns:
  id, category, priority, needs_review
needs_review is "yes" or "no". For a ticket sent to review, category and priority
may be left empty.
