import traceback
from data_loader import get_stock_data

try:
    res = get_stock_data("sk하이닉스", is_kr=True)
    print(res)
except Exception as e:
    traceback.print_exc()
