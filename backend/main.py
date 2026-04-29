from fastapi import FastAPI, Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, distinct
from database import SessionLocal, engine, Base, ETFList, ETFPriceDaily, ETFConstituent
from scheduler import start_scheduler, get_last_updated, init_history, get_history_progress
from contextlib import asynccontextmanager
from typing import Optional
from classifier import ALL_ASSET_TYPES, ALL_REGIONS, ALL_SECTORS, ALL_MANAGERS

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield

app = FastAPI(lifespan=lifespan)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ──────────────────────────────────────────────
# /api/etfs — 필터 + 페이지네이션
# ──────────────────────────────────────────────

@app.get("/api/etfs")
def get_etf_list(
    page:       int           = Query(1,  ge=1),
    page_size:  int           = Query(20, ge=1, le=100),
    asset_type: Optional[str] = Query(None),
    region:     Optional[str] = Query(None),
    sector:     Optional[str] = Query(None),
    manager:    Optional[str] = Query(None),
    search:     Optional[str] = Query(None),
    sort:       Optional[str] = Query("market_cap", description="market_cap/trade_value/return/rising/falling/volume/volume_surge/volume_drop/new_listing"),
    db: Session = Depends(get_db),
):
    """ETF 목록 + 정렬. 최신 가격과 LEFT JOIN하여 가격 기반 정렬 지원."""

    # ── 최신 날짜 서브쿼리
    latest_date_sq = (
        db.query(
            ETFPriceDaily.ticker,
            func.max(ETFPriceDaily.date).label("latest_date"),
        )
        .group_by(ETFPriceDaily.ticker)
        .subquery()
    )

    # ── 최신 가격 서브쿼리
    lp = (
        db.query(ETFPriceDaily)
        .join(
            latest_date_sq,
            and_(
                ETFPriceDaily.ticker == latest_date_sq.c.ticker,
                ETFPriceDaily.date   == latest_date_sq.c.latest_date,
            ),
        )
        .subquery()
    )


    # ── 등락률 / 거래대금 표현식 (정렬에 사용)
    chg_expr = (lp.c.close - lp.c.open) * 100.0 / func.nullif(lp.c.open, 0)
    tv_expr  = func.coalesce(lp.c.trade_value, lp.c.close * lp.c.volume)

    # ── 메인 쿼리: ETFList + 최신 가격 컬럼 (labeled)
    q = db.query(
        ETFList,
        lp.c.close.label("lp_close"),
        lp.c.open.label("lp_open"),
        lp.c.volume.label("lp_volume"),
        lp.c.trade_value.label("lp_trade_value"),
        lp.c.date.label("lp_date"),
    ).outerjoin(lp, ETFList.ticker == lp.c.ticker)

    # ── 필터
    if asset_type: q = q.filter(ETFList.asset_type == asset_type)
    if region:     q = q.filter(ETFList.region == region)
    if sector:     q = q.filter(ETFList.sector == sector)
    if manager:    q = q.filter(ETFList.manager == manager)
    if search:     q = q.filter(ETFList.name.ilike(f"%{search}%"))

    # ── 등락률 표현식
    chg_expr = (lp.c.close - lp.c.open) * 100.0 / func.nullif(lp.c.open, 0)

    # ── 상승/하락 전용 필터
    if sort == "rising":
        q = q.filter(lp.c.close > lp.c.open)
    elif sort == "falling":
        q = q.filter(lp.c.close < lp.c.open)

    total_count = q.with_entities(func.count(ETFList.id)).scalar()

    # ── 정렬
    order_map = {
        "market_cap":   ETFList.market_cap.desc(),
        "trade_value":  tv_expr.desc(),
        "return":       chg_expr.desc(),
        "rising":       chg_expr.desc(),
        "falling":      chg_expr.asc(),
        "volume":       lp.c.volume.desc(),
        "volume_surge": lp.c.volume.desc(),
        "volume_drop":  lp.c.volume.asc(),
        "new_listing":  ETFList.id.desc(),
    }
    q = q.order_by(order_map.get(sort, ETFList.market_cap.desc()))

    rows = (
        q.offset((page - 1) * page_size)
         .limit(page_size)
         .all()
    )

    result = []
    for row in rows:
        etf      = row[0]           # ETFList ORM 객체
        p_close  = row.lp_close
        p_open   = row.lp_open
        p_vol    = row.lp_volume
        p_tv     = row.lp_trade_value
        p_date   = str(row.lp_date) if row.lp_date else None

        chg_val  = round(p_close - p_open, 2) if (p_close and p_open) else None
        chg_rate = round((p_close - p_open) / p_open * 100, 2) if (p_close and p_open and p_open != 0) else None
        t_value  = int(p_tv) if p_tv else (int(p_close * p_vol) if (p_close and p_vol) else None)

        result.append({
            "ticker":      etf.ticker,
            "name":        etf.name,
            "asset_type":  etf.asset_type,
            "region":      etf.region,
            "sector":      etf.sector,
            "manager":     etf.manager,
            "market_cap":  etf.market_cap,
            "close":       p_close,
            "change_val":  chg_val,
            "change_rate": chg_rate,
            "volume":      p_vol,
            "trade_value": t_value,
            "date":        p_date,
        })

    return {
        "total":       total_count,
        "page":        page,
        "page_size":   page_size,
        "total_pages": max(1, (total_count + page_size - 1) // page_size),
        "items":       result,
    }




# ──────────────────────────────────────────────
# /api/categories — 분류 선택지 + 종목 수
# ──────────────────────────────────────────────

@app.get("/api/categories")
def get_categories(db: Session = Depends(get_db)):
    """
    각 분류 차원의 선택지와 종목 수를 반환합니다.
    프론트엔드 필터 UI 구성에 사용합니다.
    """
    def count_by(col):
        rows = (
            db.query(col, func.count(ETFList.id))
            .filter(col.isnot(None))
            .group_by(col)
            .order_by(func.count(ETFList.id).desc())
            .all()
        )
        return [{"value": r[0], "count": r[1]} for r in rows]

    return {
        "asset_types": count_by(ETFList.asset_type),
        "regions":     count_by(ETFList.region),
        "sectors":     count_by(ETFList.sector),
        "managers":    count_by(ETFList.manager),
    }


# ──────────────────────────────────────────────
# 기타 엔드포인트
# ──────────────────────────────────────────────

@app.get("/api/etfs/{ticker}")
def get_etf_detail(ticker: str, db: Session = Depends(get_db)):
    """ETF 상세 정보: 시세 + 투자정보 + 수익률"""
    import datetime as dt_mod

    etf = db.query(ETFList).filter(ETFList.ticker == ticker).first()
    if not etf:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="ETF not found")

    # 최신 시세
    latest = (
        db.query(ETFPriceDaily)
        .filter(ETFPriceDaily.ticker == ticker)
        .order_by(ETFPriceDaily.date.desc())
        .first()
    )

    # 수익률 계산용: 과거 특정 날짜 종가
    def get_close_n_months_ago(months: int):
        target_date = (
            db.query(ETFPriceDaily.date)
            .filter(ETFPriceDaily.ticker == ticker)
            .filter(ETFPriceDaily.date <= (dt_mod.date.today() - dt_mod.timedelta(days=months * 30)))
            .order_by(ETFPriceDaily.date.desc())
            .limit(1)
            .scalar()
        )
        if not target_date:
            return None
        row = (
            db.query(ETFPriceDaily)
            .filter(ETFPriceDaily.ticker == ticker, ETFPriceDaily.date == target_date)
            .first()
        )
        return row.close if row else None

    current_close = latest.close if latest else None

    def calc_return(past_close):
        if past_close and current_close:
            return round((current_close - past_close) / past_close * 100, 2)
        return None

    close_1m = get_close_n_months_ago(1)
    close_3m = get_close_n_months_ago(3)
    close_6m = get_close_n_months_ago(6)
    close_1y = get_close_n_months_ago(12)

    # 전일 종가: open 필드에 역산값 저장됨
    prev_close = latest.open if latest else None
    change_val = round(current_close - prev_close, 2) if (current_close and prev_close) else None
    change_rate = (
        round((current_close - prev_close) / prev_close * 100, 2)
        if (current_close and prev_close and prev_close != 0) else None
    )

    # 거래대금: trade_value 컬럼 우선, 없으면 close * volume 계산
    trade_value = None
    if latest:
        if latest.trade_value:
            trade_value = int(latest.trade_value)
        elif latest.close and latest.volume:
            trade_value = int(latest.close * latest.volume)

    return {
        "ticker":       etf.ticker,
        "name":         etf.name,
        "asset_type":   etf.asset_type,
        "region":       etf.region,
        "sector":       etf.sector,
        "manager":      etf.manager,
        "market_cap":   etf.market_cap,   # 억원
        # 시세 정보
        "date":         str(latest.date) if latest else None,
        "close":        current_close,
        "prev_close":   prev_close,
        "open":         prev_close,   # 스케줄러 구조상 open = prev_close
        "high":         latest.high if latest else None,
        "low":          latest.low if latest else None,
        "volume":       latest.volume if latest else None,
        "trade_value":  trade_value,
        "change_val":   change_val,
        "change_rate":  change_rate,
        # 수익률
        "return_1m":    calc_return(close_1m),
        "return_3m":    calc_return(close_3m),
        "return_6m":    calc_return(close_6m),
        "return_1y":    calc_return(close_1y),
    }


@app.get("/api/etfs/{ticker}/constituents")
def get_etf_constituents(ticker: str, db: Session = Depends(get_db)):
    rows = (
        db.query(ETFConstituent)
        .filter(ETFConstituent.etf_ticker == ticker)
        .order_by(ETFConstituent.weight.desc())
        .all()
    )
    return [
        {
            "stock_ticker": r.stock_ticker,
            "stock_name":   r.stock_name,
            "weight":       r.weight,
        }
        for r in rows
    ]


@app.get("/api/stocks/etfs")
def get_etfs_by_stock(
    ticker: Optional[str] = Query(None, description="종목 코드 (6자리, 없으면 name으로 검색)"),
    name:   Optional[str] = Query(None, description="종목명 (ticker가 없을 때 사용)"),
    db: Session = Depends(get_db),
):
    """특정 주식 종목을 구성종목으로 포함하는 ETF 목록 반환. 비중 내림차순."""
    if not ticker and not name:
        return []

    # ticker 있으면 ticker 우선, 없으면 name으로 검색
    if ticker:
        q = db.query(ETFConstituent, ETFList).join(
            ETFList, ETFConstituent.etf_ticker == ETFList.ticker
        ).filter(ETFConstituent.stock_ticker == ticker)
    else:
        q = db.query(ETFConstituent, ETFList).join(
            ETFList, ETFConstituent.etf_ticker == ETFList.ticker
        ).filter(ETFConstituent.stock_name == name)

    rows = q.order_by(ETFConstituent.weight.desc()).all()

    return [
        {
            "etf_ticker":  r.ETFConstituent.etf_ticker,
            "etf_name":    r.ETFList.name,
            "weight":      r.ETFConstituent.weight,
            "manager":     r.ETFList.manager,
            "market_cap":  r.ETFList.market_cap,
            "asset_type":  r.ETFList.asset_type,
        }
        for r in rows
    ]


@app.get("/api/etfs/{ticker}/history")
def get_etf_history(
    ticker: str,
    period:   str = Query("1y",  description="조회 기간: 1m/3m/6m/1y/5y"),
    interval: str = Query("day", description="봉 유형: day/week/month/year"),
    db: Session = Depends(get_db),
):
    """차트용 OHLCV 히스토리. period × interval 조합 지원."""
    import datetime as dt_mod

    period_map = {"1m": 30, "3m": 90, "6m": 180, "1y": 365, "5y": 365 * 5}
    days  = period_map.get(period, 365)
    since = dt_mod.date.today() - dt_mod.timedelta(days=days)

    rows = (
        db.query(ETFPriceDaily)
        .filter(ETFPriceDaily.ticker == ticker, ETFPriceDaily.date >= since)
        .order_by(ETFPriceDaily.date.asc())
        .all()
    )

    if not rows:
        return []

    # ── 일봉: 그대로 반환
    if interval == "day":
        return [
            {
                "date":   str(r.date),
                "open":   r.open,
                "high":   r.high,
                "low":    r.low,
                "close":  r.close,
                "volume": r.volume,
            }
            for r in rows
        ]

    # ── 주봉 / 월봉 / 년봉: groupby 집계
    def period_key(d: dt_mod.date) -> str:
        if interval == "week":
            # ISO 연-주차
            iso = d.isocalendar()
            return f"{iso.year}-W{iso.week:02d}"
        elif interval == "month":
            return f"{d.year}-{d.month:02d}"
        else:  # year
            return str(d.year)

    from itertools import groupby as igrp

    result = []
    for key, group in igrp(rows, key=lambda r: period_key(r.date)):
        candles = list(group)
        opens   = [c.open  for c in candles if c.open  is not None]
        highs   = [c.high  for c in candles if c.high  is not None]
        lows    = [c.low   for c in candles if c.low   is not None]
        closes  = [c.close for c in candles if c.close is not None]
        vols    = [c.volume for c in candles if c.volume is not None]

        result.append({
            "date":   str(candles[0].date),   # 기간 첫 거래일
            "open":   opens[0]  if opens  else None,
            "high":   max(highs) if highs else None,
            "low":    min(lows)  if lows  else None,
            "close":  closes[-1] if closes else None,
            "volume": sum(vols)  if vols  else None,
        })

    return result


@app.get("/api/last-updated")
def get_last_updated_time(db: Session = Depends(get_db)):
    """마지막 가격 갱신 시각 반환 (KST). 스케줄러 변수 → DB 최신 날짜 순으로 조회."""
    import datetime as dt_module
    import pytz
    kst = pytz.timezone("Asia/Seoul")

    # 1순위: 스케줄러가 기록한 정확한 갱신 시각
    ts = get_last_updated()
    if ts is not None:
        return {
            "last_updated": ts.isoformat(),
            "formatted": ts.strftime("%Y.%m.%d %H:%M"),
            "source": "scheduler",
        }

    # 2순위: DB에서 가장 최근 ETFPriceDaily 날짜 조회
    latest_date = db.query(func.max(ETFPriceDaily.date)).scalar()
    if latest_date is not None:
        combined = dt_module.datetime.combine(latest_date, dt_module.time(0, 0))
        combined_kst = kst.localize(combined)
        return {
            "last_updated": combined_kst.isoformat(),
            "formatted": latest_date.strftime("%Y.%m.%d") + " (날짜 기준)",
            "source": "db",
        }

    return {"last_updated": None, "formatted": "아직 갱신 전", "source": None}

@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# ──────────────────────────────────────────────
# /api/admin — 관리 작업 (one-time 수집 등)
# ──────────────────────────────────────────────

@app.post("/api/admin/trigger-price-update")
def trigger_price_update(background_tasks: BackgroundTasks):
    """ETF 전체 가격을 즉시 갱신합니다 (장 외 시간에도 강제 실행)."""
    from scheduler import update_price_30min
    background_tasks.add_task(update_price_30min)
    return {"status": "started", "message": "ETF 가격 즉시 갱신 시작"}


@app.post("/api/admin/trigger-master-update")
def trigger_master_update(background_tasks: BackgroundTasks):
    """ETF 종목 목록과 구성종목 정보를 즉시 갱신합니다."""
    from scheduler import update_etf_list, update_constituent
    
    def full_master_task():
        update_etf_list()
        update_constituent()
        
    background_tasks.add_task(full_master_task)
    return {"status": "started", "message": "ETF 마스터 정보 수집 시작"}


@app.post("/api/admin/init-history")
def trigger_init_history(
    background_tasks: BackgroundTasks,
    count: int = Query(365, ge=30, le=1500, description="수집할 일 수 (기본 365일, 최대 1500일)"),
):
    """
    전체 ETF 일별 OHLCV 히스토리 수집을 백그라운드로 시작합니다.
    - 네이버 fchart XML API 사용 (종목당 1 request)
    - 1,095개 기준 약 3분 소요
    - 이미 있는 데이터는 upsert (실제 open/high/low로 보정)
    """
    progress = get_history_progress()
    if progress["status"] == "running":
        return {
            "status": "already_running",
            "message": f"수집 중입니다 ({progress['done']}/{progress['total']})",
        }

    background_tasks.add_task(init_history, count)
    return {
        "status": "started",
        "message": f"ETF 히스토리 수집 시작 (최근 {count}일치)",
    }


@app.get("/api/admin/history-progress")
def history_progress():
    """init_history 진행 상황을 확인합니다."""
    p = get_history_progress()
    pct = round(p["done"] / p["total"] * 100, 1) if p["total"] > 0 else 0
    return {**p, "percent": pct}
