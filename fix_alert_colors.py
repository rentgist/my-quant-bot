with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_code = '''        if kr_risk_alerts:
            st.markdown("---")
            st.markdown("**🚨 4대 매크로 센서 상세 경보 내역**")
            for icon, msg in kr_risk_alerts:
                if icon == "🟢":
                    icon = "🔵" # 파란등 요청 반영
                st.markdown(f"{icon} {msg}") # 글머리 기호(-) 제거하여 깔끔하게'''

new_code = '''        if kr_risk_alerts:
            st.markdown("---")
            st.markdown("**🚨 4대 매크로 센서 상세 경보 내역**")
            for icon, msg in kr_risk_alerts:
                # 대장님 요청에 따라 '위험'은 빨강, '안전'은 파랑으로 엄격히 통일
                if icon in ["🔴", "🟠", "🟡"]:
                    icon = "🔴"
                else:
                    icon = "🔵"
                st.markdown(f"{icon} {msg}")'''

content = content.replace(old_code, new_code)

with open(r'C:\Users\로컬\Desktop\my-quant-bot\final.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Alert colors strictly forced to Red/Blue.")
