"""
전체 ETF 종목 목록 및 가격 데이터 + 분류 정보를 즉시 수집하는 초기화 스크립트.
네이버 증권 ETF API를 사용 (인증 불필요).

실행 방법:
  docker exec etf_backend python init_data.py
  또는:
  cd backend && python init_data.py
"""
import datetime
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

import pytz
from database import SessionLocal, ETFList, ETFPriceDaily
from scheduler import fetch_naver_etf_all, _upsert_price
from classifier import classify_etf

kst = pytz.timezone("Asia/Seoul")


def init_etf_list_and_prices():
    db = SessionLocal()
    try:
        logger.info("⏳ 네이버 증권 ETF API로 전체 종목 + 시세 조회 중...")
        items = fetch_naver_etf_all()
        if not items:
            logger.error("❌ ETF 목록을 가져오지 못했습니다.")
            return

        logger.info(f"✅ {len(items)}개 ETF 수신")
        today = datetime.datetime.now(kst).date()

        saved = updated = price_saved = 0
        for item in items:
            ticker    = str(item.get("itemcode", "")).zfill(6)
            name      = item.get("itemname", "")
            naver_tab = int(item.get("etfTabCode", 0))

            if not ticker or not name:
                continue

            # 분류 계산
            cls = classify_etf(name, naver_tab)

            existing = db.query(ETFList).filter(ETFList.ticker == ticker).first()
            if not existing:
                db.add(ETFList(
                    ticker=ticker, name=name,
                    asset_type=cls["asset_type"],
                    region=cls["region"],
                    sector=cls["sector"],
                    manager=cls["manager"],
                ))
                saved += 1
            else:
                existing.name       = name
                existing.asset_type = cls["asset_type"]
                existing.region     = cls["region"]
                existing.sector     = cls["sector"]
                existing.manager    = cls["manager"]
                updated += 1

            _upsert_price(db, ticker, item, today)
            price_saved += 1

        db.commit()
        logger.info(f"✅ 종목: 신규 {saved}개, 갱신 {updated}개")
        logger.info(f"✅ 가격: {price_saved}개 저장 완료")

        # 분류 통계 출력
        from sqlalchemy import func
        for col_name, col in [
            ("자산유형", ETFList.asset_type),
            ("투자지역", ETFList.region),
            ("운용사",   ETFList.manager),
        ]:
            rows = db.query(col, func.count(ETFList.id)).group_by(col).order_by(func.count(ETFList.id).desc()).all()
            logger.info(f"\n📊 {col_name} 분류:")
            for val, cnt in rows[:10]:
                logger.info(f"   {val or '미분류':15s} : {cnt:4d}개")

    except Exception as e:
        db.rollback()
        logger.error(f"❌ 오류 발생: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("🚀 ETF 전체 종목 초기화 시작")
    logger.info("=" * 50)
    init_etf_list_and_prices()
    logger.info("=" * 50)
    logger.info("🏁 완료")
    logger.info("=" * 50)
