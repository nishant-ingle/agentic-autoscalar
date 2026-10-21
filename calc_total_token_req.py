import json
from collections import defaultdict
from pathlib import Path

LOG_FILE = Path("usage_log.jsonl")

if not LOG_FILE.exists():
    print("No log file found yet. Run weather.py first.")
    exit()

total_requests = 0
total_input_tokens = 0
total_output_tokens = 0
daily_stats = defaultdict(lambda: {"requests": 0, "tokens": 0})

with open(LOG_FILE, "r") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        
        # Aggregate totals
        reqs = record.get("requests", 1)
        in_tok = record.get("input_tokens", 0)
        out_tok = record.get("output_tokens", 0)
        
        total_requests += reqs
        total_input_tokens += in_tok
        total_output_tokens += out_tok
        
        # Aggregate by YYYY-MM-DD
        date_str = record["timestamp"][:10]
        daily_stats[date_str]["requests"] += reqs
        daily_stats[date_str]["tokens"] += (in_tok + out_tok)

print("=" * 45)
print("📈 CUMULATIVE USAGE TOTALS")
print("=" * 45)
print(f"Total Requests Executed : {total_requests:,}")
print(f"Total Input Tokens      : {total_input_tokens:,}")
print(f"Total Output Tokens     : {total_output_tokens:,}")
print(f"Grand Total Tokens      : {total_input_tokens + total_output_tokens:,}")

print("\n📅 DAILY BREAKDOWN")
print("-" * 45)
for date, stats in sorted(daily_stats.items()):
    print(f"Date: {date} | Requests: {stats['requests']:<5} | Tokens: {stats['tokens']:,}")
print("=" * 45)