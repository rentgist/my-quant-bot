with open('data_loader.py', 'r', encoding='utf-8') as f:
    content = f.read()

import time
ts = int(time.time())

# We have two URLs to cache bust
url1 = 'remote_url = "https://raw.githubusercontent.com/rentgist/quant-alpha-engine/main/data/news_archive.json"'
new_url1 = f'remote_url = "https://raw.githubusercontent.com/rentgist/quant-alpha-engine/main/data/news_archive.json?t={ts}"'

url2 = 'remote_url = "https://raw.githubusercontent.com/rentgist/quant-alpha-engine/main/data/us_flow_report.md"'
new_url2 = f'remote_url = "https://raw.githubusercontent.com/rentgist/quant-alpha-engine/main/data/us_flow_report.md?t={ts}"'

content = content.replace(url1, new_url1).replace(url2, new_url2)

# invalidate streamlit cache again
content = content.replace('@st.cache_data(ttl=599)', '@st.cache_data(ttl=598)')

with open('data_loader.py', 'w', encoding='utf-8') as f:
    f.write(content)
