with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "위험 경보치" in line:
        for j in range(i-5, i+5):
            if 0 <= j < len(lines):
                print(f"{j+1}: {lines[j].rstrip()}")
        break
