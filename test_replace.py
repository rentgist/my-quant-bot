with open(r'C:\Users\로컬\Desktop\my-quant-bot\data_loader.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = '''            try:
                hist = fetch_fdr_history(raw_code, start=start).dropna()
            except Exception as e:
                print(f"FDR failed for {raw_code} ({e}), falling back to yfinance...")
                hist = fetch_ticker_history(yf_code, period="1y").dropna()
            tk   = yf.Ticker(yf_code)
            ticker_str = raw_code'''

replacement = '''            try:
                hist = fetch_fdr_history(raw_code, start=start).dropna()
            except Exception as e:
                hist = pd.DataFrame()
            if hist.empty or len(hist) < 30:
                print(f"FDR empty for {raw_code}, falling back to yfinance...")
                hist = fetch_ticker_history(yf_code, period="1y").dropna()
            tk   = yf.Ticker(yf_code)
            ticker_str = raw_code'''

if target in content:
    content = content.replace(target, replacement)
    with open(r'C:\Users\로컬\Desktop\my-quant-bot\data_loader.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Success")
else:
    print("Target not found!")
