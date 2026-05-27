import datetime
import pandas as pd
from pykrx_openapi import KRXOpenAPI

# 발급받은 인증키
auth_key = "378C8AF757164D28BF711836AA97DBB589D7F59E"
krx = KRXOpenAPI(api_key=auth_key)

# 최근 영업일 (20260428이 확실히 데이터가 나옴)
target_date = "20260428"
print(f"테스트 날짜: {target_date}")

def test_generic(name, category, endpoint):
    print(f"\n--- Testing Generic: {name} ({category}/{endpoint}) ---")
    try:
        # _make_request는 (category, endpoint, bas_dd)를 인자로 받음
        result = krx._make_request(category, endpoint, target_date)
        if result and "OutBlock_1" in result and result["OutBlock_1"]:
            print(f"Success! Data count: {len(result['OutBlock_1'])}")
            print("Preview:", result["OutBlock_1"][0])
        else:
            print("Success (No Data or Empty)")
    except Exception as e:
        print(f"Failed: {e}")

# 1. 주식 기본 정보 (이미 확인됨)
test_generic("Stock Base Info", "sto", "stk_isu_base_info")

# 2. ETF 기본 정보 (추측 엔드포인트)
test_generic("ETF Base Info", "etp", "etf_isu_base_info")

# 3. ETF 구성종목/PDF (추측 엔드포인트)
test_generic("ETF Constituents (PDF)", "etp", "etf_pdf_trd")

# 4. ETF 투자지표 (추측 엔드포인트)
test_generic("ETF Investment Indicators", "etp", "etf_invst_idx")
