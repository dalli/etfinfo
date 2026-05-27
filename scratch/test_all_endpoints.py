import datetime
from pykrx_openapi import KRXOpenAPI
from pykrx_openapi.constants import ENDPOINTS

# 발급받은 인증키
auth_key = "378C8AF757164D28BF711836AA97DBB589D7F59E"
krx = KRXOpenAPI(api_key=auth_key)

# 최근 영업일
target_date = "20260428"
print(f"테스트 날짜: {target_date}")

results = []

for endpoint, (category, name) in ENDPOINTS.items():
    try:
        result = krx._make_request(category, endpoint, target_date)
        status = "✅ Success" if result and "OutBlock_1" in result else "⚠️ Empty"
        count = len(result.get("OutBlock_1", []))
    except Exception as e:
        status = f"❌ Failed: {str(e)[:50]}"
        count = 0
    
    results.append({
        "name": name,
        "endpoint": f"{category}/{endpoint}",
        "status": status,
        "count": count
    })

# 결과 출력
print(f"{'API 명':<30} | {'엔드포인트':<30} | {'상태':<15} | {'데이터 수'}")
print("-" * 90)
for r in results:
    print(f"{r['name']:<30} | {r['endpoint']:<30} | {r['status']:<15} | {r['count']}")
