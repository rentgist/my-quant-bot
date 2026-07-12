import sys
import codecs
sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
from data_loader import get_krx_mapping
mapping = get_krx_mapping()
print("sk하이닉스 in mapping:", "sk하이닉스" in mapping)
print("sk하이닉스.upper() in mapping:", "sk하이닉스".upper() in mapping)
