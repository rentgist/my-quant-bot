with open('data_loader.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('@st.cache_data(ttl=600)', '@st.cache_data(ttl=599)')

with open('data_loader.py', 'w', encoding='utf-8') as f:
    f.write(content)
