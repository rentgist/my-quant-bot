import yfinance as yf
samsung = yf.Ticker('005930.KS').history(period='5d')
print(samsung)
