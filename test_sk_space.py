from data_loader import get_stock_data
res = get_stock_data("sk 하이닉스", is_kr=True)
print("Error with space:", res.get("error"))
