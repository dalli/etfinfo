import datetime
from pykrx_openapi import KRXOpenAPI

# 발급받은 인증키 설정
auth_key = "D8B43DB4ED5F44158D23788AA75F28D12829AAD2"
krx = KRXOpenAPI(api_key=auth_key)

# 오늘 날짜 확인 (최근 영업일 기준 조회가 안전함)
today = datetime.datetime.now().strftime("%Y%m%d")
yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")

print(f"=== KRX OpenAPI 테스트 ===")
print(f"조회 날짜: {today}")

# ETF 일별 거래 데이터 (이 라이브러리에서 지원하는 기능)
print("\n--- ETF 일별 거래 ---")
result = krx.get_etf_daily_trade(bas_dd=yesterday)
print(type(result))
if isinstance(result, dict):
    print("키:", list(result.keys()))
    # 첫 번째 키의 데이터 미리보기
    for k, v in result.items():
        print(f"{k}: {str(v)[:200]}")
        break
elif hasattr(result, 'head'):
    print(result.head(10))
else:
    print(result)
