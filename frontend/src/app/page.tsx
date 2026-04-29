"use client";
import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import styles from "./page.module.css";

interface ETFItem {
  ticker: string;
  name: string;
  asset_type: string | null;
  region: string | null;
  sector: string | null;
  manager: string | null;
  market_cap: number | null;
  close: number | null;
  change_val: number | null;
  change_rate: number | null;
  volume: number | null;
  trade_value: number | null;
  date: string | null;
}

interface ETFResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  items: ETFItem[];
}

interface CategoryItem { value: string; count: number; }
interface Categories {
  asset_types: CategoryItem[];
  regions:     CategoryItem[];
  sectors:     CategoryItem[];
  managers:    CategoryItem[];
}

const PAGE_SIZE = 20;
const API_BASE = typeof window !== "undefined" 
  ? (process.env.NEXT_PUBLIC_API_URL && process.env.NEXT_PUBLIC_API_URL !== "undefined" ? process.env.NEXT_PUBLIC_API_URL : "")
  : (process.env.NEXT_PUBLIC_API_URL || "");

function formatPrice(v: number | null) {
  if (v == null) return "-";
  return "₩" + v.toLocaleString("ko-KR");
}
function formatChangeVal(v: number | null) {
  if (v == null) return "-";
  const sign = v > 0 ? "+" : "";
  return sign + v.toLocaleString("ko-KR");
}
function formatChangeRate(v: number | null) {
  if (v == null) return { text: "-", cls: "" };
  const text = (v > 0 ? "+" : "") + v.toFixed(2) + "%";
  const cls  = v > 0 ? "positive" : v < 0 ? "negative" : "neutral";
  return { text, cls };
}
function formatVolume(v: number | null) {
  if (v == null) return "-";
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + "M";
  if (v >= 1_000)     return (v / 1_000).toFixed(1) + "K";
  return v.toLocaleString("ko-KR");
}
function formatTradeValue(v: number | null) {
  if (v == null) return "-";
  if (v >= 1_000_000_000_000) return (v / 1_000_000_000_000).toFixed(1) + "조";
  if (v >= 100_000_000)       return Math.floor(v / 100_000_000).toLocaleString("ko-KR") + "억";
  if (v >= 10_000)            return Math.floor(v / 10_000).toLocaleString("ko-KR") + "만";
  return v.toLocaleString("ko-KR") + "원";
}
function formatMarketCap(v: number | null) {
  if (v == null) return "-";
  // market_cap은 억원 단위
  if (v >= 10_000) return (v / 10_000).toFixed(1) + "조";
  return v.toLocaleString("ko-KR") + "억";
}

// ── 자산유형 탭 순서
const ASSET_TYPE_TABS = [
  "전체", "국내주식", "해외주식", "채권", "원자재",
  "부동산", "통화", "레버리지", "인버스", "혼합",
];

export default function Home() {
  const router = useRouter();
  const [data,        setData]        = useState<ETFResponse | null>(null);
  const [categories,  setCategories]  = useState<Categories | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [page,        setPage]        = useState(1);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState(false);

  // ── 필터 상태
  const [assetType, setAssetType] = useState("전체");
  const [region,    setRegion]    = useState("");
  const [sector,    setSector]    = useState("");
  const [manager,   setManager]   = useState("");
  const [search,    setSearch]    = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [sort,      setSort]      = useState("market_cap");

  // 카테고리 목록 + 갱신 시각 로드
  useEffect(() => {
    fetch(`${API_BASE}/api/categories`)
      .then(r => r.json())
      .then(setCategories)
      .catch(() => {});

    // 갱신 시각 폴링 (5분마다)
    const fetchLastUpdated = () =>
      fetch(`${API_BASE}/api/last-updated`)
        .then(r => r.json())
        .then(d => setLastUpdated(d.formatted))
        .catch(() => {});
    fetchLastUpdated();
    const timer = setInterval(fetchLastUpdated, 5 * 60 * 1000);
    return () => clearInterval(timer);
  }, []);

  const fetchEtfs = useCallback(async (p: number) => {
    setLoading(true);
    setError(false);
    try {
      const params = new URLSearchParams({ page: String(p), page_size: String(PAGE_SIZE) });
      if (assetType && assetType !== "전체") params.set("asset_type", assetType);
      if (region)  params.set("region",  region);
      if (sector)  params.set("sector",  sector);
      if (manager) params.set("manager", manager);
      if (search)  params.set("search",  search);
      if (sort)    params.set("sort",    sort);

      const res  = await fetch(`${API_BASE}/api/etfs?${params}`);
      if (!res.ok) throw new Error("API error");
      const json: ETFResponse = await res.json();
      setData(json);
    } catch {
      setError(true);
      setData({ total: 0, page: p, page_size: PAGE_SIZE, total_pages: 1, items: [] });
    } finally {
      setLoading(false);
    }
  }, [assetType, region, sector, manager, search, sort]);

  // 필터나 페이지 변경 시 재조회
  useEffect(() => {
    fetchEtfs(page);
  }, [page, fetchEtfs]);

  // 필터 변경 시 page 리셋
  const handleAssetType = (v: string) => { setAssetType(v); setPage(1); };
  const handleRegion    = (v: string) => { setRegion(v);    setPage(1); };
  const handleSector    = (v: string) => { setSector(v);    setPage(1); };
  const handleManager   = (v: string) => { setManager(v);   setPage(1); };
  const handleSort      = (v: string) => { setSort(v);      setPage(1); };
  const handleSearch    = () => { setSearch(searchInput); setPage(1); };
  const handleClearAll  = () => {
    setAssetType("전체"); setRegion(""); setSector(""); setManager("");
    setSearch(""); setSearchInput(""); setSort("market_cap"); setPage(1);
  };

  const items      = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;
  const total      = data?.total ?? 0;

  // 페이지네이션
  const pageGroupSize = 5;
  const currentGroup  = Math.floor((page - 1) / pageGroupSize);
  const groupStart    = currentGroup * pageGroupSize + 1;
  const groupEnd      = Math.min(groupStart + pageGroupSize - 1, totalPages);
  const pageButtons   = Array.from({ length: groupEnd - groupStart + 1 }, (_, i) => groupStart + i);

  const hasFilter = assetType !== "전체" || region || sector || manager || search;

  return (
    <div className="dashboard-container">
      {/* ── Header ── */}
      <header className="header">
        <div>
          <h1>Korea ETF Monitor</h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginTop: "0.25rem" }}>
            국내 상장 ETF 전종목 · 30분 지연 시세
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--text-secondary)" }}>
          <span className="live-indicator"></span>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.1rem" }}>
            <span style={{ fontSize: "0.8rem" }}>갱신</span>
            <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)" }}>
              {lastUpdated ?? "--"}
            </span>
          </div>
          {error && (
            <span style={{ fontSize: "0.75rem", color: "#f59e0b", marginLeft: "0.5rem" }}>
              ⚠ Demo Mode
            </span>
          )}
        </div>
      </header>

      {/* ── 자산유형 탭 ── */}
      <div className={styles.assetTabs}>
        {ASSET_TYPE_TABS.map(tab => (
          <button
            key={tab}
            className={`${styles.assetTab} ${assetType === tab ? styles.assetTabActive : ""}`}
            onClick={() => handleAssetType(tab)}
          >
            {tab}
            {tab !== "전체" && categories?.asset_types.find(a => a.value === tab) && (
              <span className={styles.tabCount}>
                {categories.asset_types.find(a => a.value === tab)?.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── 세부 필터 바 ── */}
      <div className={styles.filterBar}>
        {/* 검색 + 정렬 */}
        <div className={styles.searchWrap}>
          <input
            className={styles.searchInput}
            type="text"
            placeholder="종목명 검색..."
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleSearch()}
          />
          <button className={styles.searchBtn} onClick={handleSearch}>🔍</button>
        </div>

        {/* 정렬 기준 */}
        <select
          className={styles.filterSelect}
          value={sort}
          onChange={e => handleSort(e.target.value)}
          style={{ fontWeight: 600 }}
        >
          <option value="market_cap">📦 운용자산 순</option>
          <option value="trade_value">💸 거래대금 순</option>
          <option value="return">📈 수익률 순</option>
          <option value="rising">🔴 상승 상위</option>
          <option value="falling">🔵 하락 상위</option>
          <option value="volume">🔥 거래량 상위</option>
          <option value="volume_surge">⚡ 거래량 급증</option>
          <option value="volume_drop">❄️ 거래량 급감</option>
          <option value="new_listing">🆕 신규상장</option>
        </select>

        {/* 투자지역 */}
        <select
          className={styles.filterSelect}
          value={region}
          onChange={e => handleRegion(e.target.value)}
        >
          <option value="">🌏 전체 지역</option>
          {categories?.regions.map(r => (
            <option key={r.value} value={r.value}>{r.value} ({r.count})</option>
          ))}
        </select>

        {/* 섹터 */}
        <select
          className={styles.filterSelect}
          value={sector}
          onChange={e => handleSector(e.target.value)}
        >
          <option value="">📂 전체 섹터</option>
          {categories?.sectors.map(s => (
            <option key={s.value} value={s.value}>{s.value} ({s.count})</option>
          ))}
        </select>

        {/* 운용사 */}
        <select
          className={styles.filterSelect}
          value={manager}
          onChange={e => handleManager(e.target.value)}
        >
          <option value="">🏢 전체 운용사</option>
          {categories?.managers.map(m => (
            <option key={m.value} value={m.value}>{m.value} ({m.count})</option>
          ))}
        </select>

        {/* 필터 초기화 */}
        {hasFilter && (
          <button className={styles.clearBtn} onClick={handleClearAll}>
            ✕ 초기화
          </button>
        )}
      </div>

      {/* ── 종목 리스트 패널 ── */}
      <div className="glass-panel" style={{ marginBottom: "1.5rem" }}>
        {/* 패널 헤더 */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
          <h2 className="panel-title" style={{ marginBottom: 0 }}>
            📊 ETF 종목
            {total > 0 && (
              <span style={{ fontSize: "0.8rem", fontWeight: 400, color: "var(--text-secondary)", marginLeft: "0.5rem" }}>
                총 {total.toLocaleString()}개
              </span>
            )}
          </h2>
          <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
            {page} / {totalPages} 페이지
          </span>
        </div>

        {/* 테이블 */}
        {loading ? (
          <div className={styles.loadingWrap}>
            <div className={styles.spinner}></div>
            <p style={{ color: "var(--text-secondary)", marginTop: "1rem" }}>데이터 로딩 중...</p>
          </div>
        ) : items.length === 0 ? (
          <div className={styles.loadingWrap}>
            <p style={{ color: "var(--text-secondary)" }}>조건에 맞는 종목이 없습니다.</p>
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: "40px" }}>No.</th>
                  <th>종목명</th>
                  <th style={{ textAlign: "right" }}>현재가</th>
                  <th style={{ textAlign: "right" }}>전일대비</th>
                  <th style={{ textAlign: "right" }}>거래량</th>
                  <th style={{ textAlign: "right" }}>거래대금</th>
                  <th style={{ textAlign: "right" }}>운용자산</th>
                </tr>
              </thead>
              <tbody>
                {items.map((etf, idx) => {
                  const { text: changeText, cls: changeCls } = formatChangeRate(etf.change_rate);
                  const changeValCls = etf.change_val != null ? (etf.change_val > 0 ? "positive" : etf.change_val < 0 ? "negative" : "neutral") : "";
                  const rowNum = (page - 1) * PAGE_SIZE + idx + 1;
                  return (
                    <tr key={etf.ticker} className={styles.tableRow} onClick={() => router.push(`/etf/${etf.ticker}`)}>
                      <td style={{ color: "var(--text-secondary)", fontSize: "0.8rem" }}>{rowNum}</td>
                      <td>
                        <div style={{ fontWeight: 600 }}>{etf.name}</div>
                        <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: "2px", display: "flex", gap: "4px" }}>
                          <span>{etf.ticker}</span>
                          {etf.manager && <span style={{ opacity: 0.7 }}>· {etf.manager}</span>}
                        </div>
                      </td>
                      <td style={{ textAlign: "right", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
                        {formatPrice(etf.close)}
                      </td>
                      <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        <div className={changeValCls} style={{ fontWeight: 600 }}>
                          {formatChangeVal(etf.change_val)}
                        </div>
                        <div className={changeCls} style={{ fontSize: "0.8rem", marginTop: "1px" }}>
                          {changeText}
                        </div>
                      </td>
                      <td style={{ textAlign: "right", color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                        {formatVolume(etf.volume)}
                      </td>
                      <td style={{ textAlign: "right", color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                        {formatTradeValue(etf.trade_value)}
                      </td>
                      <td style={{ textAlign: "right", color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                        {formatMarketCap(etf.market_cap)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* 페이지네이션 */}
        {!loading && totalPages > 1 && (
          <div className={styles.pagination}>
            <button className={styles.pageBtn} onClick={() => setPage(1)}            disabled={page === 1}>«</button>
            <button className={styles.pageBtn} onClick={() => setPage(Math.max(1, groupStart - 1))} disabled={groupStart === 1}>‹</button>
            {pageButtons.map(p => (
              <button key={p} className={`${styles.pageBtn} ${p === page ? styles.pageBtnActive : ""}`}
                onClick={() => setPage(p)}>{p}</button>
            ))}
            <button className={styles.pageBtn} onClick={() => setPage(Math.min(totalPages, groupEnd + 1))} disabled={groupEnd === totalPages}>›</button>
            <button className={styles.pageBtn} onClick={() => setPage(totalPages)}   disabled={page === totalPages}>»</button>
          </div>
        )}
      </div>
    </div>
  );
}
