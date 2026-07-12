with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if '데이터 조회 실패' in line:
        print(f"Line {i}: found it")
