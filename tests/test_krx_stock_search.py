import pandas as pd

from data_loader import (
    KRX_FALLBACK_MAPPING,
    _build_krx_mapping,
    _get_fallback_krx_mapping,
    _normalise_kr_query,
)


def test_fallback_contains_sungho_electronics():
    assert KRX_FALLBACK_MAPPING["성호전자"] == {
        "raw_code": "043260",
        "yf_code": "043260.KQ",
    }
    fallback = _get_fallback_krx_mapping()
    assert fallback["성호전자"] == fallback["043260"]
    assert fallback["SKHYNIX"]["raw_code"] == "000660"


def test_build_mapping_supports_names_codes_and_market_suffixes():
    listing = pd.DataFrame(
        [
            {"Code": "005930", "Name": "삼성전자", "Market": "KOSPI"},
            {"Code": "043260", "Name": "성호전자", "Market": "KOSDAQ"},
            {"Code": "123456", "Name": "코스닥 글로벌", "Market": "KOSDAQ GLOBAL"},
            {"Code": "999999", "Name": "코넥스 테스트", "Market": "KONEX"},
        ]
    )

    mapping = _build_krx_mapping(listing)

    assert mapping["삼성전자"]["yf_code"] == "005930.KS"
    assert mapping["성호전자"]["yf_code"] == "043260.KQ"
    assert mapping["043260"] == mapping["성호전자"]
    assert mapping["코스닥글로벌"]["yf_code"] == "123456.KQ"
    assert "999999" not in mapping
    assert "코넥스 테스트" not in mapping


def test_normalise_kr_query_removes_spaces_and_case_difference():
    assert _normalise_kr_query("  ls electric ") == "LSELECTRIC"
