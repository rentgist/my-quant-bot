with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the broken multiline function call comment
broken_code = '''#         kr_rec_verdict, kr_rec_signals, kr_rec_score = calculate_kr_recovery_confirmation(
            kospi_10y, usd_krw
        )'''

fixed_code = '''#         kr_rec_verdict, kr_rec_signals, kr_rec_score = calculate_kr_recovery_confirmation(
#             kospi_10y, usd_krw
#         )'''

content = content.replace(broken_code, fixed_code)

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Indentation error fixed.")
