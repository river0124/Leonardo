

import json

input_path = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/우선주리스트.txt"
output_path = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/preferred_stock_list.json"

preferred_stock_codes = []

with open(input_path, "r", encoding="utf-8") as infile:
    for line in infile:
        parts = line.strip().split(",")
        if len(parts) > 1:
            preferred_stock_codes.append(parts[1])

with open(output_path, "w", encoding="utf-8") as outfile:
    json.dump(preferred_stock_codes, outfile, ensure_ascii=False, indent=2)

print(f"✅ {len(preferred_stock_codes)} 종목 코드 저장 완료 → {output_path}")