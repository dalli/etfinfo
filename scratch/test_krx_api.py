import datetime
import pandas as pd
from pykrx_openapi import KRXOpenAPI

# 발급받은 인증키
auth_key = "378C8AF757164D28BF711836AA97DBB589D7F59E"
krx = KRXOpenAPI(api_key=auth_key)

# 최근 영업일 (안전하게 1일 전)
yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")

print(f"테스트 날짜: {yesterday}")

def test_api(name, func, **kwargs):
    print(f"\n--- Testing: {name} ---")
    try:
        result = func(**kwargs)
        if result is not None:
            print(f"Success! Type: {type(result)}")
            if hasattr(result, 'head'):
                print(result.head(3))
            elif isinstance(result, dict):
                print("Keys:", list(result.keys())[:5])
            else:
                print(str(result)[:200])
        else:
            print("Returned None")
    except Exception as e:
        print(f"Failed: {e}")

# 1. ETF 일별 시세 (이미 확인됨)
test_api("ETF Daily Trade", krx.get_etf_daily_trade, bas_dd=yesterday)

# 2. 주식 기본 정보 (이게 ETF도 포함하는지 확인)
test_api("Stock Base Info", krx.get_stock_base_info, bas_dd=yesterday)

# 3. ESG ETP 정보
test_api("ESG ETP Info", krx.get_esg_etp_info, bas_dd=yesterday)

# 4. KRX 전체 시세
test_api("KRX Daily Trade", krx.get_krx_daily_trade, bas_dd=yesterday)
