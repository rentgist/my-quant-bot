# 🤖 ORION Quant Bot: AI Context & Changelog

## 📌 Project Overview
- **Name**: ORION Quant Dashboard
- **Type**: Streamlit-based Web Application (inal.py is the main entry point)
- **Purpose**: Macro-economic analysis, regime classification, and dynamic portfolio rebalancing advice.

## 🏗️ Architecture & Key Files
- inal.py: The Streamlit dashboard UI and layout logic. Contains the main tabs (🇰🇷 ORION Signal, 🇺🇸 ORION Signal, 종목 발굴 & 타이밍, etc.).
- signals.py: Core logic for signal generation (Macro Risk Gauge, Bottom Finder, US Macro Score).
- data_loader.py: Data fetching engine. Connects to yfinance, KRX, and FRED (via pandas_datareader) to fetch multi-asset class data (VIX, DXY, HY Spread, Yield Curve, BTC, SPY, KOSPI).
- portfolio_manager.py: Parses the local Markdown portfolio logs (portfolio_log_YYYYMMDD.md) using Regex to extract current holdings for real-time dashboard linking.
- i_reporter.py: Generates the dynamic rebalancing text (The "AI Control Room" report and custom portfolio strategies based on Guru logic: Buffett, Druckenmiller, Fisher).
- egime_state.json: Used for tracking market regime states (e.g. Warning days) to persist logic across reruns.

## 🔄 Recent Updates (Last Session - 2026.08.06)
- **UI Refactoring**: 
  - Separated the primary ORION Signal tab into US (🦅) and KR (🐯) specific tabs for better modularity.
  - Moved the AI 참모 리포트 under the 종목 발굴 & 타이밍 tab.
- **US Macro Engine Implementation**:
  - Implemented calculate_us_orion_score in signals.py.
  - Added real-time FRED data ingestion for Fed Liquidity (WALCL, WTREGEN, RRPONTSYD) and BofA High Yield Spread.
  - Added Market Breadth (RSP vs SPY) and Aux (BTC) scoring.
- **Dynamic Portfolio Advisor**:
  - Connected portfolio_manager.py to parse US holdings (e.g. TSMC, NVDA, MSFT).
  - Wrote dynamic reporting logic in i_reporter.py that outputs different rebalancing advice for user-held tech stocks depending on the current Macro Phase (CLEAR / CAUTION / ALERT).

## 🛑 Agent Rules & Directives
- **Strict Verification Protocol (.agents/rules/strict_verification.md)**: You MUST read and scan code before modifying. After modifying, you MUST compile (python -m py_compile) and verify functionality before reporting completion. Do not assume file structures blindly.
