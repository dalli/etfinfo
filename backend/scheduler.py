"""
ETF 데이터 수집 스케줄러
- 데이터 소스: 네이버 증권 ETF API (인증 불필요, 전체 1,095개 종목 한 번에)
- 필드: 현재가(nowVal), 등락률(changeRate), 거래량(quant), 거래대금(amonut)
- 분류: classifier.py의 classify_etf()로 자산유형/지역/섹터/운용사 자동 분류
"""
import logging
import datetime
import time

import requests
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from database import SessionLocal, ETFList, ETFPriceIntraday, ETFPriceDaily, ETFConstituent
from classifier import classify_etf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

kst = pytz.timezone("Asia/Seoul")

# 마지막 가격 갱신 시각 (KST) — API로 노출
_last_updated: datetime.datetime | None = None

def get_last_updated() -> datetime.datetime | None:
    return _last_updated

# ──────────────────────────────────────────────
# 네이버 증권 ETF API
# ──────────────────────────────────────────────

NAVER_ETF_LIST_URL = "https://finance.naver.com/api/sise/etfItemList.nhn"
NAVER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/etf/",
}

def fetch_naver_etf_all() -> list[dict]:
    """
    네이버 증권 ETF API로 전체 ETF 목록 + 현재 시세를 한 번에 가져옵니다.
    인증 불필요. 1,000개 이상 종목을 단일 요청으로 반환.

    반환 필드:
      itemcode     : KRX 6자리 티커
      itemname     : 종목명
      nowVal       : 현재가 (원)
      changeVal    : 전일 대비 변화 (원)
      changeRate   : 등락률 (%)  — 양수=상승, 음수=하락
      risefall     : "1"=하락, "2"=상승, "3"=보합
      quant        : 거래량
      amonut       : 거래대금 (백만원)
      nav          : 순자산가치 (NAV)
      marketSum    : 시가총액 (억원)
    """
    try:
        resp = requests.get(NAVER_ETF_LIST_URL, headers=NAVER_HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("result", {}).get("etfItemList", [])
        logger.info(f"네이버 ETF API: {len(items)}개 수신")
        return items
    except Exception as e:
        logger.error(f"네이버 ETF API 조회 실패: {e}")
        return []


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _is_market_open() -> bool:
    """KST 기준 평일 09:00~15:30"""
    now = datetime.datetime.now(kst)
    if now.date().weekday() >= 5:
        return False
    market_open  = now.replace(hour=9,  minute=0,  second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


# ──────────────────────────────────────────────
# 스케줄 작업
# ──────────────────────────────────────────────

def update_etf_list():
    """
    [08:30] 매일 장 시작 전 — 전체 ETF 종목명 갱신.
    네이버 API 한 번으로 종목명 + 최신 시세 동시 저장.
    """
    logger.info("[Task] update_etf_list 시작")
    items = fetch_naver_etf_all()
    if not items:
        logger.warning("[Task] update_etf_list: 데이터 없음")
        return

    db = next(get_db())
    try:
        today = datetime.datetime.now(kst).date()
        saved = updated = 0

        for item in items:
            ticker = str(item.get("itemcode", "")).zfill(6)
            name   = item.get("itemname", "")
            if not ticker or not name:
                continue

            # 분류 계산
            naver_tab = int(item.get("etfTabCode", 0))
            cls = classify_etf(name, naver_tab)

            # ETFList upsert (분류 포함)
            existing = db.query(ETFList).filter(ETFList.ticker == ticker).first()
            if not existing:
                db.add(ETFList(
                    ticker=ticker, name=name,
                    asset_type=cls["asset_type"],
                    region=cls["region"],
                    sector=cls["sector"],
                    manager=cls["manager"],
                    market_cap=float(item.get("marketSum") or 0) or None,
                ))
                saved += 1
            else:
                existing.name       = name
                existing.asset_type = cls["asset_type"]
                existing.region     = cls["region"]
                existing.sector     = cls["sector"]
                existing.manager    = cls["manager"]
                existing.market_cap = float(item.get("marketSum") or 0) or None
                updated += 1

            # 시세도 동시에 저장
            _upsert_price(db, ticker, item, today)

        db.commit()
        logger.info(f"[Task] update_etf_list 완료 — 신규 {saved}개, 갱신 {updated}개")
    except Exception as e:
        db.rollback()
        logger.error(f"[Task] update_etf_list 실패: {e}", exc_info=True)
    finally:
        db.close()


def update_price_30min():
    """
    [30분 주기] 전체 ETF 현재 시세 갱신.
    - 장 외 시간에는 자동 스킵.
    - DB ETFList에 있는 종목만 upsert.
    """
    now = datetime.datetime.now(kst)
    if not _is_market_open():
        logger.info(f"[Task] update_price_30min 스킵 (장 외: {now.strftime('%H:%M %a')})")
        return

    logger.info(f"[Task] update_price_30min 시작 ({now.strftime('%H:%M')})")
    items = fetch_naver_etf_all()
    if not items:
        return

    db = next(get_db())
    try:
        today = now.date()
        # DB 기존 종목 티커 세트 (빠른 조회용)
        existing_tickers = {t.ticker for t in db.query(ETFList.ticker).all()}

        upserted = 0
        new_etfs  = 0
        for item in items:
            ticker = str(item.get("itemcode", "")).zfill(6)
            if not ticker:
                continue

            # 신규 상장 종목 자동 추가 (분류 포함)
            if ticker not in existing_tickers:
                name = item.get("itemname", ticker)
                naver_tab = int(item.get("etfTabCode", 0))
                cls = classify_etf(name, naver_tab)
                db.add(ETFList(
                    ticker=ticker, name=name,
                    asset_type=cls["asset_type"],
                    region=cls["region"],
                    sector=cls["sector"],
                    manager=cls["manager"],
                    market_cap=float(item.get("marketSum") or 0) or None,
                ))
                existing_tickers.add(ticker)
                new_etfs += 1
            else:
                # 기존 종목 시총 갱신
                etf_obj = db.query(ETFList).filter(ETFList.ticker == ticker).first()
                if etf_obj and item.get("marketSum"):
                    etf_obj.market_cap = float(item.get("marketSum") or 0) or None

            _upsert_price(db, ticker, item, today)
            upserted += 1

        db.commit()
        global _last_updated
        _last_updated = datetime.datetime.now(kst)
        msg = f"[Task] update_price_30min 완료 — {upserted}개 갱신"
        if new_etfs:
            msg += f", {new_etfs}개 신규 종목 추가"
        logger.info(msg)
    except Exception as e:
        db.rollback()
        logger.error(f"[Task] update_price_30min 실패: {e}", exc_info=True)
    finally:
        db.close()


def update_daily_close():
    """[16:00] 장 마감 확정 종가 저장. update_price_30min과 동일 로직."""
    logger.info("[Task] update_daily_close 시작")
    items = fetch_naver_etf_all()
    if not items:
        return

    db = next(get_db())
    try:
        today = datetime.datetime.now(kst).date()
        upserted = 0
        for item in items:
            ticker = str(item.get("itemcode", "")).zfill(6)
            if ticker:
                _upsert_price(db, ticker, item, today)
                upserted += 1
        db.commit()
        logger.info(f"[Task] update_daily_close 완료 — {upserted}개 확정 종가 저장")
    except Exception as e:
        db.rollback()
        logger.error(f"[Task] update_daily_close 실패: {e}", exc_info=True)
    finally:
        db.close()


def _upsert_price(db, ticker: str, item: dict, trade_date: datetime.date):
    """ETFPriceDaily upsert 헬퍼 — PostgreSQL ON CONFLICT DO UPDATE 사용"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    close_p = float(item.get("nowVal") or 0)
    if close_p == 0:
        return

    change_val  = float(item.get("changeVal") or 0)
    volume      = int(item.get("quant") or 0)
    # amonut는 백만원 단위 → 원 단위로 변환
    trade_value = int((item.get("amonut") or 0)) * 1_000_000
    # 전일 종가 역산: 현재가 - 변화분
    prev_close  = close_p - change_val
    open_p = prev_close if prev_close > 0 else close_p

    stmt = pg_insert(ETFPriceDaily).values(
        ticker=ticker,
        date=trade_date,
        open=open_p,
        high=close_p,
        low=close_p,
        close=close_p,
        volume=volume,
        trade_value=float(trade_value) if trade_value > 0 else None,
    ).on_conflict_do_update(
        constraint="uq_etf_price_daily_ticker_date",
        set_={
            "close":       close_p,
            "open":        open_p,
            "volume":      volume,
            "trade_value": float(trade_value) if trade_value > 0 else ETFPriceDaily.trade_value,
        }
    )
    # ORM 세션 identity map을 우회해 raw connection으로 실행
    # → RETURNING id가 세션 캐시와 충돌하는 문제 방지
    db.connection().execute(stmt)


# ──────────────────────────────────────────────
# 1년치 히스토리 수집 (네이버 fchart XML API)
# data: 날짜|시가|고가|저가|종가|거래량
# ──────────────────────────────────────────────

NAVER_FCHART_URL = (
    "https://fchart.stock.naver.com/sise.nhn"
    "?symbol={ticker}&timeframe=day&count={count}&requestType=0"
)

# 진행 상태 공유 (API로 조회 가능)
_history_progress: dict = {"status": "idle", "done": 0, "total": 0, "errors": 0}

def get_history_progress() -> dict:
    return _history_progress.copy()


def fetch_etf_ohlcv(ticker: str, count: int = 365) -> list[dict]:
    """
    네이버 fchart API로 일별 OHLCV 수집 (종목당 1 request).
    반환: [{date, open, high, low, close, volume}, ...]
    """
    from xml.etree import ElementTree as ET

    url = NAVER_FCHART_URL.format(ticker=ticker, count=count)
    try:
        resp = requests.get(url, headers=NAVER_HEADERS, timeout=15)
        resp.encoding = "euc-kr"
        root = ET.fromstring(resp.text)
    except Exception as e:
        logger.warning(f"[히스토리] {ticker} 요청 실패: {e}")
        return []

    records = []
    for item in root.findall(".//item"):
        data = item.get("data", "")
        parts = data.split("|")
        if len(parts) < 6:
            continue
        try:
            date_str, open_s, high_s, low_s, close_s, vol_s = parts[:6]
            records.append({
                "date":   datetime.datetime.strptime(date_str, "%Y%m%d").date(),
                "open":   float(open_s),
                "high":   float(high_s),
                "low":    float(low_s),
                "close":  float(close_s),
                "volume": int(vol_s),
            })
        except Exception:
            continue
    return records


def _upsert_history_records(db, ticker: str, records: list[dict]):
    """날짜별 OHLCV를 ETFPriceDaily에 upsert (존재하면 갱신, 없으면 삽입)."""
    if not records:
        return

    existing_dates = {
        r.date
        for r in db.query(ETFPriceDaily.date)
        .filter(ETFPriceDaily.ticker == ticker)
        .all()
    }

    to_insert = []
    to_update = []
    for r in records:
        if r["date"] in existing_dates:
            to_update.append(r)
        else:
            to_insert.append(r)

    # 신규 삽입
    for r in to_insert:
        db.add(ETFPriceDaily(
            ticker=ticker,
            date=r["date"],
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"],
        ))

    # 기존 갱신 (open/high/low가 없거나 잘못된 것 보정)
    for r in to_update:
        db.query(ETFPriceDaily).filter(
            ETFPriceDaily.ticker == ticker,
            ETFPriceDaily.date == r["date"],
        ).update({
            "open":   r["open"],
            "high":   r["high"],
            "low":    r["low"],
            "close":  r["close"],
            "volume": r["volume"],
        }, synchronize_session=False)


def init_history(count: int = 365):
    """
    전체 ETF 1년치 OHLCV 히스토리 초기 수집.
    - 종목당 1 HTTP 요청 (fchart XML)
    - 0.15초 간격으로 서버 부하 방지
    - 이미 데이터가 있는 날짜는 갱신 (open/high/low 보정 포함)
    """
    global _history_progress
    _history_progress = {"status": "running", "done": 0, "total": 0, "errors": 0}

    db = next(get_db())
    try:
        tickers = [r.ticker for r in db.query(ETFList.ticker).all()]
        total = len(tickers)
        _history_progress["total"] = total
        logger.info(f"[히스토리] 수집 시작 — {total}개 ETF × 최근 {count}일")

        for i, ticker in enumerate(tickers):
            try:
                records = fetch_etf_ohlcv(ticker, count)
                if records:
                    _upsert_history_records(db, ticker, records)

                _history_progress["done"] = i + 1

                # 100개마다 커밋 + 로그
                if (i + 1) % 100 == 0:
                    db.commit()
                    logger.info(
                        f"[히스토리] 진행 중: {i + 1}/{total} "
                        f"(오류: {_history_progress['errors']})"
                    )

                time.sleep(0.15)

            except Exception as e:
                logger.warning(f"[히스토리] {ticker} 실패: {e}")
                _history_progress["errors"] += 1
                continue

        db.commit()
        _history_progress["status"] = "done"
        logger.info(
            f"[히스토리] 완료 — {total}개 처리, "
            f"오류 {_history_progress['errors']}개"
        )

    except Exception as e:
        db.rollback()
        _history_progress["status"] = "error"
        logger.error(f"[히스토리] 전체 실패: {e}", exc_info=True)
    finally:
        db.close()


# ──────────────────────────────────────────────
# 구성종목 수집 (네이버 증권 HTML 파싱)
# ──────────────────────────────────────────────

NAVER_ITEM_URL = "https://finance.naver.com/item/main.naver?code={ticker}"

def fetch_constituents(ticker: str) -> list[dict]:
    """
    네이버 증권 ETF 상세 페이지에서 구성종목(상위 10개)을 파싱합니다.
    반환: [{stock_ticker, stock_name, weight}, ...]
    """
    import re
    from bs4 import BeautifulSoup

    url = NAVER_ITEM_URL.format(ticker=ticker)
    try:
        resp = requests.get(url, headers=NAVER_HEADERS, timeout=15)
        resp.encoding = resp.apparent_encoding  # euc-kr 하드코딩 대신 자동 감지
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        logger.warning(f"[구성종목] {ticker} 페이지 요청 실패: {e}")
        return []

    # 구성종목 테이블: 헤더에 '구성종목' 포함하는 테이블 탐색
    target_table = None
    for tbl in soup.find_all('table'):
        rows = tbl.find_all('tr')
        if rows and '구성종목' in rows[0].get_text():
            target_table = tbl
            break

    if target_table is None:
        return []

    results = []
    for row in target_table.find_all('tr')[1:]:
        cells = row.find_all('td')
        if not cells or len(cells) < 3:
            continue

        # 국내 ETF: 종목명에 <a> 링크 + code 파라미터 있음
        link = row.find('a', href=True)
        if link:
            m = re.search(r'code=(\d+)', link['href'])
            stock_ticker = m.group(1) if m else ""
            stock_name   = link.get_text(strip=True)
        else:
            # 해외 ETF: 링크 없이 텍스트만
            stock_ticker = ""
            stock_name   = cells[0].get_text(strip=True)

        if not stock_name:
            continue

        weight_text = cells[2].get_text(strip=True).replace(',', '').replace('%', '')
        try:
            weight = float(weight_text) if weight_text and weight_text != '-' else 0.0
        except ValueError:
            weight = 0.0

        results.append({
            "stock_ticker": stock_ticker,
            "stock_name":   stock_name,
            "weight":       weight,
        })
    return results


def update_constituents():
    """
    [매일 07:00] 전체 ETF 구성종목 갱신.
    - DB에 등록된 ETF 전종목 대상으로 순차 수집.
    - 기존 구성종목 삭제 후 재삽입 방식 (항상 최신 상태 유지).
    - 네이버 서버 부하 방지를 위해 요청 간 0.3초 대기.
    """
    logger.info("[Task] update_constituents 시작")
    db = next(get_db())
    try:
        tickers = [r.ticker for r in db.query(ETFList.ticker).all()]
        total   = len(tickers)
        success = 0
        skipped = 0
        today   = datetime.datetime.now(kst).date()

        for i, ticker in enumerate(tickers):
            try:
                items = fetch_constituents(ticker)
                if not items:
                    skipped += 1
                    continue

                # 기존 구성종목 삭제
                db.query(ETFConstituent).filter(
                    ETFConstituent.etf_ticker == ticker
                ).delete(synchronize_session=False)

                # 신규 삽입
                for item in items:
                    db.add(ETFConstituent(
                        etf_ticker   = ticker,
                        stock_ticker = item["stock_ticker"],
                        stock_name   = item["stock_name"],
                        weight       = item["weight"],
                        update_date  = today,
                    ))

                success += 1

                # 100개마다 중간 커밋 + 로그
                if success % 100 == 0:
                    db.commit()
                    logger.info(f"[Task] update_constituents 진행 중: {success}/{total}")

                time.sleep(0.3)  # 네이버 서버 부하 방지

            except Exception as e:
                logger.warning(f"[Task] update_constituents {ticker} 실패: {e}")
                skipped += 1
                continue

        db.commit()
        logger.info(f"[Task] update_constituents 완료 — 성공 {success}개 / 건너뜀 {skipped}개")

    except Exception as e:
        db.rollback()
        logger.error(f"[Task] update_constituents 전체 실패: {e}", exc_info=True)
    finally:
        db.close()


def start_scheduler():
    scheduler = BackgroundScheduler(timezone=kst)

    # 1. 매일 08:30 — 종목 목록 갱신
    scheduler.add_job(
        update_etf_list,
        CronTrigger(hour=8, minute=30, timezone=kst),
        id="update_etf_list",
        name="ETF 종목 목록 갱신",
        replace_existing=True,
    )

    # 2. 30분 주기 — 시세 갱신 (앱 시작 즉시 첫 실행)
    scheduler.add_job(
        update_price_30min,
        IntervalTrigger(minutes=30, timezone=kst),
        id="update_price_30min",
        name="ETF 전체 가격 30분 갱신",
        replace_existing=True,
        next_run_time=datetime.datetime.now(kst),
    )

    # 3. 매일 16:00 — 확정 종가
    scheduler.add_job(
        update_daily_close,
        CronTrigger(hour=16, minute=0, timezone=kst),
        id="update_daily_close",
        name="ETF 확정 종가 저장",
        replace_existing=True,
    )

    # 4. 매일 07:00 — 구성종목 갱신 (장 시작 전, 전 종목 순차 수집)
    scheduler.add_job(
        update_constituents,
        CronTrigger(hour=7, minute=0, timezone=kst),
        id="update_constituents",
        name="ETF 구성종목 갱신",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("✅ 스케줄러 시작")
    logger.info("  - 07:00     : ETF 구성종목 갱신 (네이버 증권 HTML 파싱)")
    logger.info("  - 08:30     : ETF 종목 목록 + 시세 갱신 (네이버 증권)")
    logger.info("  - 30분 주기 : 전체 ETF 시세 갱신 (장중에만)")
    logger.info("  - 16:00     : 확정 종가 저장")

