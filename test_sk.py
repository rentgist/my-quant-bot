import FinanceDataReader as fdr
df = fdr.StockListing('KRX')
sk = df[df['Name'].str.contains('하이닉스', na=False, case=False)]
print(sk)
