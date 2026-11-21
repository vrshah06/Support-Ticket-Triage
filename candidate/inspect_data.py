import csv
import os

csv_path = os.path.join(os.path.dirname(__file__), "tickets.csv")

with open(csv_path, mode="r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    tickets = list(reader)

print(f"Total tickets: {len(tickets)}")
print("Fields:", reader.fieldnames)

# Check missing values
for col in reader.fieldnames:
    missing = [t["id"] for t in tickets if not t.get(col, "").strip()]
    print(f"Column '{col}' empty count: {len(missing)}")
    if missing:
        print(f"  IDs with empty '{col}': {missing}")

# Check body length stats
lens = [len(t.get("body", "").strip()) for t in tickets]
print(f"Body length - Min: {min(lens)}, Max: {max(lens)}, Avg: {sum(lens)/len(lens):.1f}")

# Look at short or unusual bodies
short = [t for t in tickets if len(t.get("body", "").strip()) < 15]
print(f"Short bodies count: {len(short)}")
for s in short:
    print(f"  {s['id']} | Subject: {s['subject']} | Body: {repr(s['body'])}")
