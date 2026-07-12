from data_loader import get_krx_mapping
krx_dict = get_krx_mapping()
print('SK하이닉스' in krx_dict)
print(krx_dict.get('SK하이닉스'))
