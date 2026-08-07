import os

for fname in ['ai_reporter.py', 'signals.py', 'final.py']:
    if os.path.exists(fname):
        with open(fname, 'r', encoding='utf-8') as f:
            content = f.read()
        content = content.replace('gemini-2.5-flash', 'gemini-1.5-flash')
        with open(fname, 'w', encoding='utf-8') as f:
            f.write(content)

print("Replaced gemini-2.5-flash with 1.5")
