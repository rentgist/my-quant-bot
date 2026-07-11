from data_loader import get_stock_data
import sys

try:
    print("Testing 브로드컴...")
    res1 = get_stock_data("브로드컴", is_kr=False, fast_mode=False)
    print("브로드컴:", res1.get("error"), res1.get("Price"))

    print("Testing SK하이닉스...")
    res2 = get_stock_data("sk하이닉스", is_kr=True, fast_mode=False)
    print("SK하이닉스:", res2.get("error"), res2.get("Price"))
except Exception as e:
    print("Exception:", e)
