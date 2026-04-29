"""
ETF 자동 분류 로직
ETF 이름(name)과 네이버 탭 코드(naver_tab)를 기반으로 4가지 분류 차원을 반환합니다.

분류 차원:
  asset_type : 자산유형  (국내주식 / 해외주식 / 채권 / 원자재 / 부동산 / 통화 / 레버리지 / 인버스 / 혼합)
  region     : 투자지역  (국내 / 미국 / 중국 / 일본 / 유럽 / 인도 / 신흥국 / 글로벌 / 기타)
  sector     : 섹터/테마 (반도체 / 2차전지 / AI·로봇 / 바이오 / 금융 / 에너지 / 소비재 / 방산 / ESG / 배당 / 부동산 / None)
  manager    : 운용사    (KODEX / TIGER / ACE / RISE / SOL / PLUS / KOSEF / HANARO / HK / KBSTAR / 기타)
"""

import re

# ──────────────────────────────────────────────
# 자산유형 (etfTabCode → 한글)
# ──────────────────────────────────────────────

_ASSET_TYPE_MAP = {
    1: "국내주식",
    2: "해외주식",
    3: "채권",
    4: "원자재",
    5: "부동산",
    6: "통화",
    7: "레버리지",
    8: "인버스",
    9: "혼합",
}


def _classify_asset_type(naver_tab: int, name: str) -> str:
    """etfTabCode 기반 자산유형. 이름에 레버리지/인버스가 있으면 오버라이드."""
    # 이름 기반 레버리지/인버스 보완 (네이버 탭이 주식으로 분류되는 경우 있음)
    name_lower = name.lower()
    if any(k in name for k in ["레버리지", "Leverage", "2X", "3X"]):
        return "레버리지"
    if any(k in name for k in ["인버스", "Inverse", "-1X", "-2X"]):
        return "인버스"
    return _ASSET_TYPE_MAP.get(naver_tab, "기타")


# ──────────────────────────────────────────────
# 투자지역
# ──────────────────────────────────────────────

# 순서가 중요: 더 구체적인 항목이 먼저 와야 함
_REGION_RULES: list[tuple[list[str], str]] = [
    # 미국
    (["미국", "S&P", "나스닥", "NYSE", "다우", "DOW", "SP500", "Nasdaq", "러셀", "FANG", "빅테크",
      "월가", "미채", "미국채", "달러"], "미국"),
    # 중국
    (["중국", "차이나", "China", "항셍", "항항", "HSI", "CSI", "홍콩", "H주", "홍콩H"], "중국"),
    # 일본
    (["일본", "Japan", "재팬", "닛케이", "Nikkei", "엔화"], "일본"),
    # 유럽
    (["유럽", "유로", "Euro", "Stoxx", "유로스탁스", "영국", "독일", "프랑스"], "유럽"),
    # 인도
    (["인도", "India", "Nifty", "Nifty50", "인디아"], "인도"),
    # 베트남
    (["베트남", "Vietnam", "VN"], "베트남"),
    # 인도네시아
    (["인도네시아"], "인도네시아"),
    # 신흥국
    (["신흥국", "이머징", "Emerging", "EM", "브릭스", "BRICs"], "신흥국"),
    # 글로벌
    (["글로벌", "Global", "World", "세계", "선진국"], "글로벌"),
    # 국내 (명시적 한국 키워드 + 국내 지수)
    (["코스피", "코스닥", "KOSPI", "KOSDAQ", "KRX", "KTOP",
      "200", "150", "국내", "한국", "KQ", "K200", "코리아"], "국내"),
]

_DOMESTIC_ASSET_TABS = {1}   # 국내주식 탭 → 지역 기본값=국내
_FOREIGN_BOND_TABS   = {2}   # 해외주식


def _classify_region(name: str, asset_type: str) -> str:
    for keywords, region in _REGION_RULES:
        if any(kw in name for kw in keywords):
            return region
    # 자산유형 기반 기본값
    if asset_type in ("국내주식", "레버리지", "인버스"):
        return "국내"
    if asset_type == "채권":
        # 채권 이름에 지역 언급 없으면 국내 채권
        return "국내"
    return "기타"


# ──────────────────────────────────────────────
# 섹터/테마
# ──────────────────────────────────────────────

_SECTOR_RULES: list[tuple[list[str], str]] = [
    (["반도체", "Semiconductor", "SEMICON", "SOX", "팹리스", "웨이퍼", "HBM"], "반도체"),
    (["2차전지", "배터리", "Battery", "리튬", "전기차", "EV", "LFP"], "2차전지"),
    (["AI", "인공지능", "로봇", "Robot", "자동화", "드론", "머신러닝", "GPT"], "AI·로봇"),
    (["바이오", "Bio", "헬스케어", "Healthcare", "제약", "의료", "헬스", "메디컬"], "바이오·헬스"),
    (["금융", "은행", "Bank", "보험", "증권", "Financial", "핀테크"], "금융"),
    (["에너지", "Energy", "원유", "Oil", "가스", "LNG", "태양광", "신재생", "친환경", "탄소"], "에너지"),
    (["소비재", "소비", "유통", "Retail", "브랜드", "Consumer", "경기소비"], "소비재"),
    (["방산", "항공우주", "Defense", "우주", "Space", "방위"], "방산·우주"),
    (["ESG", "친환경", "Green", "저탄소", "탄소중립"], "ESG"),
    (["배당", "Dividend", "고배당", "분배", "월배당", "커버드콜"], "배당"),
    (["리츠", "REITs", "부동산", "Real Estate", "인프라", "Infrastructure"], "부동산·인프라"),
    (["통신", "5G", "Telecom", "미디어", "Media", "게임", "Entertainment", "엔터"], "통신·미디어"),
    (["원자재", "금", "Gold", "은", "Silver", "구리", "Copper", "농산물", "Commodity"], "원자재"),
    (["차이나테크", "테크", "Tech", "IT", "클라우드", "Cloud", "SaaS", "소프트웨어"], "테크·IT"),
    (["미래", "혁신", "Innovation", "테마", "트렌드", "Next"], "혁신·테마"),
]

_SECTOR_APPLICABLE_TYPES = {"국내주식", "해외주식", "레버리지", "인버스", "혼합"}


def _classify_sector(name: str, asset_type: str) -> str | None:
    for keywords, sector in _SECTOR_RULES:
        if any(kw in name for kw in keywords):
            return sector
    # 채권·원자재·부동산·통화 자산유형에서 섹터 없음
    if asset_type not in _SECTOR_APPLICABLE_TYPES:
        return None
    return None


# ──────────────────────────────────────────────
# 운용사
# ──────────────────────────────────────────────

_MANAGER_RULES: list[tuple[str, str, str]] = [
    # (브랜드명, 운용사 정식명, 이름 패턴)
    ("KODEX",    "삼성자산운용",          "KODEX"),
    ("TIGER",    "미래에셋자산운용",       "TIGER"),
    ("ACE",      "한국투자신탁운용",       "ACE"),
    ("RISE",     "KB자산운용",            "RISE"),
    ("SOL",      "신한자산운용",          "SOL"),
    ("PLUS",     "한화자산운용",          "PLUS"),
    ("KOSEF",    "키움투자자산운용",       "KOSEF"),
    ("HANARO",   "NH아문디자산운용",       "HANARO"),
    ("HK",       "하나자산운용",          "HK"),
    ("KBSTAR",   "KB자산운용",            "KBSTAR"),
    ("ARIRANG",  "한화자산운용",          "ARIRANG"),
    ("SMART",    "키움투자자산운용",       "SMART"),
    ("TREX",     "유진자산운용",          "TREX"),
    ("FOCUS",    "동양자산운용",          "FOCUS"),
    ("파워",      "교보악사자산운용",      "파워"),
    ("마이티",    "대신자산운용",          "마이티"),
    ("TIMEFOLIO","타임폴리오자산운용",    "TIMEFOLIO"),
    ("에셋플러스", "에셋플러스자산운용",   "에셋플러스"),
]


def _classify_manager(name: str) -> str:
    for brand, full_name, pattern in _MANAGER_RULES:
        if name.startswith(pattern) or name.upper().startswith(pattern.upper()):
            return brand
    return "기타"


# ──────────────────────────────────────────────
# 통합 분류 함수
# ──────────────────────────────────────────────

def classify_etf(name: str, naver_tab: int) -> dict:
    """
    ETF 이름과 네이버 탭 코드를 받아 4가지 분류를 반환합니다.

    Args:
        name      : ETF 종목명 (e.g. "KODEX 반도체")
        naver_tab : 네이버 증권 etfTabCode (1~9)

    Returns:
        {
            "asset_type": "국내주식",
            "region":     "국내",
            "sector":     "반도체",   # 없으면 None
            "manager":    "KODEX",
        }
    """
    asset_type = _classify_asset_type(naver_tab, name)
    region     = _classify_region(name, asset_type)
    sector     = _classify_sector(name, asset_type)
    manager    = _classify_manager(name)
    return {
        "asset_type": asset_type,
        "region":     region,
        "sector":     sector,
        "manager":    manager,
    }


# ──────────────────────────────────────────────
# 각 분류의 전체 값 목록 (프론트 필터용)
# ──────────────────────────────────────────────

ALL_ASSET_TYPES = ["국내주식", "해외주식", "채권", "원자재", "부동산", "통화", "레버리지", "인버스", "혼합", "기타"]
ALL_REGIONS     = ["국내", "미국", "중국", "일본", "유럽", "인도", "베트남", "인도네시아", "신흥국", "글로벌", "기타"]
ALL_SECTORS     = [
    "반도체", "2차전지", "AI·로봇", "바이오·헬스", "금융",
    "에너지", "소비재", "방산·우주", "ESG", "배당",
    "부동산·인프라", "통신·미디어", "원자재", "테크·IT", "혁신·테마",
]
ALL_MANAGERS    = [r[0] for r in _MANAGER_RULES] + ["기타"]


if __name__ == "__main__":
    # 빠른 테스트
    tests = [
        ("KODEX 반도체", 1),
        ("TIGER 미국S&P500", 2),
        ("ACE 중국본토CSI300", 2),
        ("KODEX 200선물인버스2X", 8),
        ("KOSEF 국고채10년", 3),
        ("TIGER 원유선물Enhanced(H)", 4),
        ("HANARO 글로벌인프라MLP(합성)", 2),
        ("KODEX 2차전지산업", 1),
        ("SOL 미국배당다우존스", 2),
        ("RISE 부동산리츠인프라", 5),
    ]
    for name, tab in tests:
        result = classify_etf(name, tab)
        print(f"{name:45s} → {result}")
