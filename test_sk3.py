import sys
import codecs
sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
from data_loader import get_stock_data

try:
    res = get_stock_data("sk하이닉스", is_kr=True)
    print(res.keys())
    print("error:", res.get("error"))
    print("Name:", res.get("Name"))
except Exception as e:
    import traceback
    traceback.print_exc()
