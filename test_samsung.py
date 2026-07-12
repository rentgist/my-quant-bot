import yfinance as yf
samsung = yf.Ticker('005930.KS').history(period='1d')
print(f"Samsung: {samsung['Close'].iloc[-1]}")
