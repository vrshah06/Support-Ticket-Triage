import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from processor import TicketProcessor

def run():
    processor = TicketProcessor()
    csv_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "candidate", "tickets.csv")
    with open(csv_file, "r", encoding="utf-8") as f:
        valid, errors = processor.load_and_validate_csv(f)
        if not valid:
            print("Errors:", errors)
            sys.exit(1)

    print(f"Loaded {len(processor.tickets)} tickets.")
    stats = processor.process_all_tickets(confidence_threshold=0.80)
    print("Processing completed. Summary stats:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    res_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", "results.csv")
    rep_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", "report.json")

    df = processor.export_results_csv(res_path)
    rep = processor.export_report_json(rep_path)

    print(f"\nVerification:")
    print(f"  results.csv rows: {len(df)}")
    print(f"  results.csv columns: {list(df.columns)}")
    print(f"  needs_review distribution:\n{df['needs_review'].value_counts()}")
    print(f"  report.json successfully written: {os.path.exists(rep_path)}")

if __name__ == "__main__":
    run()
