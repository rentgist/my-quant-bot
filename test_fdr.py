import FinanceDataReader as fdr
import datetime
start = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
try:
    df = fdr.DataReader('000660', start)
    print(f"Data rows: {len(df)}")
except Exception as e:
    print(f"Error: {e}")
