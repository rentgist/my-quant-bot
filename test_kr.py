import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_loader import get_macro_charts
from signals import calculate_kr_bottom_finder

print("Fetching KR data via get_macro_charts()...")
charts = get_macro_charts()

kospi = charts.get("kospi_10y")
vkospi = charts.get("vkospi_10y")
usdkrw = charts.get("usdkrw_10y")

score, verdict, details, market_phase = calculate_kr_bottom_finder(
    kospi, vkospi, usdkrw
)

print(f"\nScore: {score}")
print(f"Verdict: {verdict}")
print(f"Market Phase: {market_phase}")
print("Details:")
for d in details:
    print(f" - {d}")
