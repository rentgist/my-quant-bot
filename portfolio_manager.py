import os
import re
from pathlib import Path


PORTFOLIO_LOG_DIR = Path(__file__).resolve().parent / "data" / "portfolio-logs"

def parse_portfolio_log():
    """Read the newest dated portfolio snapshot from the managed log folder."""
    log_files = sorted(PORTFOLIO_LOG_DIR.glob("portfolio_log_*.md"))
    if not log_files:
        return {'kr': [], 'us': []}
    latest_log = log_files[-1]
    
    with latest_log.open('r', encoding='utf-8') as f:
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
