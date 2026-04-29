from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Float, DateTime, Text, Date, Boolean, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker
import datetime
import os

# Read database URL from environment variable, default to a local postgres for fallback
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://etfuser:etfpassword@localhost:5432/etfdb")

# PostgreSQL doesn't need check_same_thread
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class ETFList(Base):
    __tablename__ = "etf_list"
    id          = Column(Integer, primary_key=True, index=True)
    ticker      = Column(String, unique=True, index=True)
    name        = Column(String)
    # ── 분류 (4가지 차원)
    asset_type  = Column(String, index=True, nullable=True)   # 자산유형: 국내주식/해외주식/채권 등
    region      = Column(String, index=True, nullable=True)   # 투자지역: 국내/미국/중국 등
    sector      = Column(String, index=True, nullable=True)   # 섹터/테마: 반도체/2차전지/AI 등 (nullable)
    manager     = Column(String, index=True, nullable=True)   # 운용사: KODEX/TIGER/ACE 등
    market_cap  = Column(Float, nullable=True)                # 시가총액 (억원, 네이버 marketSum)

class ETFConstituent(Base):
    __tablename__ = "etf_constituents"
    id = Column(Integer, primary_key=True, index=True)
    etf_ticker = Column(String, index=True)
    stock_ticker = Column(String)
    stock_name = Column(String)
    weight = Column(Float)
    update_date = Column(Date, default=datetime.date.today)

class ETFPriceIntraday(Base):
    __tablename__ = "etf_price_intraday"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True)
    timestamp = Column(DateTime, index=True)
    price = Column(Float)
    volume = Column(Integer)
    retail_net = Column(Integer, nullable=True) # 매매주체 (개인) 순매수
    foreign_net = Column(Integer, nullable=True) # (외국인) 순매수
    inst_net = Column(Integer, nullable=True) # (기관) 순매수

class ETFPriceDaily(Base):
    __tablename__ = "etf_price_daily"
    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_etf_price_daily_ticker_date"),)
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True)
    date = Column(Date, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(BigInteger)
    trade_value = Column(Float, nullable=True)   # 거래대금 (원)
    retail_net = Column(BigInteger, nullable=True)
    foreign_net = Column(BigInteger, nullable=True)
    inst_net = Column(BigInteger, nullable=True)

class ETFNews(Base):
    __tablename__ = "etf_news"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True)
    title = Column(String)
    url = Column(String, unique=True)
    published_at = Column(DateTime)
    summary = Column(Text, nullable=True)

Base.metadata.create_all(bind=engine)
