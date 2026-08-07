import re

with open('signals.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Define the new code
new_code = '''def calculate_us_orion_score(macro_data):
    """
    Calculate the US ORION Signal score (0-100) based on macroeconomic and market data.
    macro_data: dict of dataframes from data_loader
    Returns: total_score, phase, score_components, triggers, metrics
    """
    score_components = {
        'macro': 0.0,
        'credit': 0.0,
        'strength': 0.0,
        'aux': 0.0
    }
    
    triggers = []
    metrics = {}
    
    # helper for safe float
    def get_last(df, col='Close'):
        if df is not None and not df.empty and col in df:
            return float(df[col].iloc[-1])
        elif df is not None and not df.empty and 'Value' in df:
            return float(df['Value'].iloc[-1])
        return None
        
    def get_rsi(df, col='Close', period=14):
        if df is not None and len(df) > period:
            from indicators import get_rolling_rsi
            rsi = get_rolling_rsi(df[col], period)
            return float(rsi.iloc[-1])
        return 50.0

    # 1. Macro Liquidity (35%)
    # Fed Liquidity = WALCL - WTREGEN - RRPONTSYD
    fed_liquidity_score = 50.0
    curr_liq = None
    if 'fred_macro' in macro_data and not macro_data['fred_macro'].empty:
        fred = macro_data['fred_macro']
        if 'WALCL' in fred and 'WTREGEN' in fred and 'RRPONTSYD' in fred:
            liquidity = fred['WALCL'] - fred['WTREGEN'] - fred['RRPONTSYD']
            if len(liquidity) > 20:
                curr_liq = liquidity.iloc[-1]
                ma20_liq = liquidity.rolling(20).mean().iloc[-1]
                metrics['net_liquidity'] = curr_liq / 1000 # in billions
                if curr_liq > ma20_liq:
                    fed_liquidity_score = 80.0
                    triggers.append(f"연준 순유동성이 20일 이평선을 상회하며 유동성 환경 양호 (현재 {curr_liq/1000:.1f}B)")
                else:
                    fed_liquidity_score = 30.0
                    triggers.append(f"연준 순유동성이 20일 이평선을 하회하며 유동성 축소 경계 (현재 {curr_liq/1000:.1f}B)")

    dxy = get_last(macro_data.get('dxy_10y'))
    dxy_score = 50.0
    if dxy:
        metrics['dxy'] = dxy
        if dxy < 103:
            dxy_score = 80.0
            triggers.append(f"달러 약세(DXY {dxy:.1f})로 글로벌 위험자산 투자 심리 긍정적")
        elif dxy > 105:
            dxy_score = 20.0
            triggers.append(f"강달러 현상(DXY {dxy:.1f})으로 인해 신흥국 및 기술주 유동성 압박 우려")
        else:
            dxy_score = 50.0

    jpy = get_last(macro_data.get('usdjpy_10y'))
    jpy_score = 50.0
    if jpy:
        jpy_ma20 = macro_data['usdjpy_10y']['Close'].rolling(20).mean().iloc[-1] if len(macro_data['usdjpy_10y']) >= 20 else jpy
        if jpy < jpy_ma20 * 0.95:
            jpy_score = 20.0
            triggers.append(f"USD/JPY 급락({jpy:.1f})으로 엔캐리 트레이드 청산 리스크 발생 주의")
        else:
            jpy_score = 70.0
            
    tnx = get_last(macro_data.get('tnx_10y'))
    irx = get_last(macro_data.get('irx_10y'))
    yield_score = 50.0
    if tnx:
        metrics['tnx'] = tnx
    if tnx and irx:
        spread = tnx - irx
        metrics['yield_spread'] = spread
        if spread > 0:
            yield_score = 80.0
        else:
            yield_score = 30.0
            triggers.append(f"장단기 금리차 역전(Spread {spread:.2f}%p)으로 거시경제 둔화 우려 지속")
        
    macro_score = (fed_liquidity_score + dxy_score + jpy_score + yield_score) / 4.0
    score_components['macro'] = macro_score * 0.35

    # 2. Credit & Psychology (35%)
    hyg_spread_score = 50.0
    hy_spread = None
    if 'fred_macro' in macro_data and 'BAMLH0A0HYM2' in macro_data['fred_macro']:
        hy_spread = macro_data['fred_macro']['BAMLH0A0HYM2'].iloc[-1]
        metrics['hy_spread'] = hy_spread
        if hy_spread < 4.0:
            hyg_spread_score = 90.0
            triggers.append(f"하이일드 스프레드({hy_spread:.2f}%) 안정권, 신용 리스크 낮음")
        elif hy_spread > 5.5:
            hyg_spread_score = 20.0
            triggers.append(f"하이일드 스프레드({hy_spread:.2f}%) 급등, 기업 신용 경색 위험 신호 발생")
        else:
            hyg_spread_score = 50.0

    vix = get_last(macro_data.get('vix_10y'))
    vix_score = 50.0
    if vix:
        metrics['vix'] = vix
        if vix < 15:
            vix_score = 90.0
        elif vix < 20:
            vix_score = 70.0
        elif vix < 30:
            vix_score = 30.0
            triggers.append(f"VIX 지수 상승({vix:.1f})으로 단기 변동성 확대 경계")
        else:
            vix_score = 10.0
            triggers.append(f"VIX 지수 폭등({vix:.1f}), 시장 공포 심리 극대화")
        
    spy_rsi = get_rsi(macro_data.get('spy_10y'))
    rsi_score = spy_rsi if spy_rsi else 50.0

    credit_score = (hyg_spread_score + vix_score + rsi_score) / 3.0
    score_components['credit'] = credit_score * 0.35

    # 3. Market Breadth (20%)
    rsp = get_last(macro_data.get('rsp_10y'))
    spy = get_last(macro_data.get('spy_10y'))
    strength_score = 50.0
    if rsp and spy:
        strength_score = 60.0
    score_components['strength'] = strength_score * 0.20

    # 4. Aux (10%)
    btc = get_last(macro_data.get('btc_10y'))
    aux_score = 50.0
    if btc:
        metrics['btc'] = btc
        btc_ma50 = macro_data['btc_10y']['Close'].rolling(50).mean().iloc[-1] if len(macro_data['btc_10y']) >= 50 else btc
        if btc > btc_ma50:
            aux_score = 80.0
            triggers.append(f"비트코인 50일선 상회로 투기적 유동성 확장 국면")
        else:
            aux_score = 30.0
            triggers.append(f"비트코인 50일선 하회로 투기 자금 축소 조짐")
            
    score_components['aux'] = aux_score * 0.10

    total_score = sum(score_components.values())
    
    if total_score >= 65:
        us_phase = "CLEAR"
    elif total_score >= 40:
        us_phase = "CAUTION"
    else:
        us_phase = "ALERT"
        
    return total_score, us_phase, score_components, triggers, metrics

def get_us_strategic_advice(us_phase, total_score, triggers):
    """
    Generate dynamic advice string based on US ORION triggers.
    """
    if us_phase == "CLEAR":
        head = "🟢 전천후 상승장 (CLEAR) - 주도주 집중"
        color = "#2e7d32"
    elif us_phase == "CAUTION":
        head = "🟡 변동성 경계 (CAUTION) - 현금 확보 및 리밸런싱"
        color = "#fbc02d"
    else:
        head = "🔴 위험 회피 (ALERT) - 방어적 자산 배분 우선"
        color = "#c62828"
        
    actions = []
    
    if triggers:
        for t in list(set(triggers)):
            actions.append(f"💡 {t}")
    else:
        actions.append("💡 주요 매크로 지표들이 중립적인 수준을 유지하고 있습니다.")
        
    if us_phase == "CLEAR":
        actions.append("🚀 **투자 전략**: 위험 자산 비중을 확대하고 AI/Tech 주도주의 추세를 추종하십시오.")
    elif us_phase == "CAUTION":
        actions.append("⚖️ **투자 전략**: 신규 투자는 보수적으로 접근하고, 포트폴리오 내 과매수 종목의 수익 실현(Trimming)을 권장합니다.")
    else:
        actions.append("🛡️ **투자 전략**: 하방 리스크가 큽니다. 단기채(SGOV 등) 및 현금 비중을 대폭 늘리십시오.")
        
    return head, color, actions
'''

start_idx = content.find('def calculate_us_orion_score(macro_data):')
end_idx = content.find('return total_score, phase, score_components', start_idx)

if start_idx != -1 and end_idx != -1:
    content_before = content[:start_idx]
    end_of_line_idx = content.find('\n', end_idx)
    content_after = content[end_of_line_idx:]
    
    final_content = content_before + new_code + content_after
    
    with open('signals.py', 'w', encoding='utf-8') as f:
        f.write(final_content)
    print("Successfully replaced calculate_us_orion_score and added get_us_strategic_advice")
else:
    print("Could not find blocks. start:", start_idx, "end:", end_idx)

