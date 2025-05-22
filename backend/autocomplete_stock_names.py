import sys
import json
import pandas as pd

def main():
    try:
        query = sys.stdin.read().strip()
        if not query:
            print("[]")
            return

        df = pd.read_csv("stock_list.csv")
        exact_match = df[df['Name'].str.lower() == query.lower()]
        contains_match = df[df['Name'].str.contains(query, case=False, na=False) & (df['Name'].str.lower() != query.lower())]
        combined = pd.concat([exact_match, contains_match]).drop_duplicates().head(10)
        result = combined[['Name', 'Code']].to_dict(orient='records')
        print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()