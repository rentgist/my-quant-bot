import os
import re

def parse_portfolio_log():
    # Find the latest portfolio_log file
    log_files = [f for f in os.listdir('.') if f.startswith('portfolio_log_') and f.endswith('.md')]
    if not log_files:
        return {'kr': [], 'us': []}
    latest_log = sorted(log_files)[-1]
    
    with open(latest_log, 'r', encoding='utf-8') as f:
        content = f.read()
        
    holdings = {'kr': [], 'us': []}
    
    # Split by sections
    kr_section = re.search(r'국내 계좌.*?\|(.*?)\n\n', content, re.DOTALL | re.IGNORECASE)
    us_section = re.search(r'해외 계좌.*?\|(.*?)(?:\n\n|\n---)', content, re.DOTALL | re.IGNORECASE)
    
    if us_section:
        us_table = us_section.group(1)
        for line in us_table.split('\n'):
            if line.strip().startswith('|') and '종목명' not in line and ':---' not in line:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 6:
                    name_col = parts[1]
                    ticker_match = re.search(r'\((.*?)\)', name_col)
                    if ticker_match:
                        holdings['us'].append(ticker_match.group(1))
    
    return holdings

if __name__ == '__main__':
    print(parse_portfolio_log())
