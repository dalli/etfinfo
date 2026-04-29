"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import styles from "./page.module.css";

/* ───── 타입 ───── */
interface ETFDetail {
  ticker: string; name: string;
  asset_type: string | null; region: string | null;
  sector: string | null; manager: string | null;
  market_cap: number | null;
  date: string | null; close: number | null; prev_close: number | null;
  open: number | null; high: number | null; low: number | null;
  volume: number | null; trade_value: number | null;
  change_val: number | null; change_rate: number | null;
  return_1m: number | null; return_3m: number | null;
  return_6m: number | null; return_1y: number | null;
}
interface Constituent { stock_ticker: string; stock_name: string; weight: number; }
interface Candle {
  date: string; open: number | null; high: number | null;
  low: number | null; close: number | null; volume: number | null;
}
interface EtfByStock {
  etf_ticker: string; etf_name: string; weight: number;
  manager: string | null; market_cap: number | null; asset_type: string | null;
}

type Interval = "day" | "week" | "month" | "year";

const API_BASE = typeof window !== "undefined" 
  ? (process.env.NEXT_PUBLIC_API_URL && process.env.NEXT_PUBLIC_API_URL !== "undefined" ? process.env.NEXT_PUBLIC_API_URL : "")
  : (process.env.NEXT_PUBLIC_API_URL || "");

/* ───── 포맷 헬퍼 ───── */
const fmt   = (v: number | null, s = "") => v == null ? "-" : v.toLocaleString("ko-KR") + s;
const fmtP  = (v: number | null) => v == null ? "-" : "₩" + v.toLocaleString("ko-KR");
const fmtMC = (v: number | null) => v == null ? "-" : v >= 10000 ? (v/10000).toFixed(1)+"조" : v.toLocaleString("ko-KR")+"억";
const fmtTV = (v: number | null) => {
  if (v == null) return "-";
  if (v >= 1_000_000_000_000) return (v/1_000_000_000_000).toFixed(1)+"조";
  if (v >= 100_000_000) return Math.floor(v/100_000_000).toLocaleString("ko-KR")+"억";
  return Math.floor(v/10_000).toLocaleString("ko-KR")+"만";
};
const fmtR  = (v: number | null) => ({
  text: v == null ? "-" : (v>0?"+":"")+v.toFixed(2)+"%",
  cls:  v == null ? styles.neutralText : v>0 ? styles.positiveText : v<0 ? styles.negativeText : styles.neutralText,
});

/* ───── 종목 → ETF 목록 모달 ───── */
function StockEtfModal({
  stock, onClose, onEtfClick,
}: {
  stock: { ticker: string; name: string };
  onClose: () => void;
  onEtfClick: (etfTicker: string) => void;
}) {
  const [list, setList]   = useState<EtfByStock[]>([]);
  const [busy, setBusy]   = useState(true);

  useEffect(() => {
    setBusy(true);
    const params = new URLSearchParams();
    if (stock.ticker) params.set("ticker", stock.ticker);
    else              params.set("name",   stock.name);
    fetch(`${API_BASE}/api/stocks/etfs?${params}`)
      .then(r => r.json())
      .then(setList)
      .catch(() => setList([]))
      .finally(() => setBusy(false));
  }, [stock.ticker, stock.name]);

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modalBox} onClick={e => e.stopPropagation()}>
        {/* 헤더 */}
        <div className={styles.modalHeader}>
          <div>
            <div className={styles.modalTitle}>{stock.name}</div>
            <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>
              {!busy && `이 종목을 포함한 ETF ${list.length}개`}
            </div>
          </div>
          <button className={styles.modalClose} onClick={onClose}>✕</button>
        </div>

        {/* 본문 */}
        {busy ? (
          <div style={{ textAlign:"center", padding:"2rem", color:"var(--text-secondary)" }}>조회 중...</div>
        ) : list.length === 0 ? (
          <div style={{ textAlign:"center", padding:"2rem", color:"var(--text-secondary)" }}>결과가 없습니다.</div>
        ) : (
          <div className={styles.modalList}>
            <table className={styles.portfolioTable}>
              <thead><tr>
                <th>#</th><th>ETF명</th><th>운용사</th>
                <th style={{ textAlign:"right" }}>구성비중</th>
                <th style={{ textAlign:"right" }}>운용자산</th>
              </tr></thead>
              <tbody>
                {list.map((e, i) => (
                  <tr key={e.etf_ticker}
                    style={{ cursor:"pointer" }}
                    className={styles.tableRowHover}
                    onClick={() => onEtfClick(e.etf_ticker)}
                  >
                    <td className={styles.rankNum}>{i+1}</td>
                    <td>
                      <div style={{ fontWeight:600 }}>{e.etf_name}</div>
                      <div style={{ fontSize:"0.75rem", color:"var(--text-secondary)" }}>{e.etf_ticker}</div>
                    </td>
                    <td style={{ color:"var(--text-secondary)", fontSize:"0.82rem", whiteSpace:"nowrap" }}>{e.manager ?? "-"}</td>
                    <td style={{ textAlign:"right", fontWeight:700 }}>
                      <span style={{ color: e.weight > 10 ? "#ef4444" : e.weight > 3 ? "#f59e0b" : "#94a3b8" }}>
                        {e.weight?.toFixed(2)}%
                      </span>
                    </td>
                    <td style={{ textAlign:"right", color:"var(--text-secondary)", fontSize:"0.82rem" }}>
                      {e.market_cap != null ? (e.market_cap >= 10000 ? (e.market_cap/10000).toFixed(1)+"조" : e.market_cap.toLocaleString()+"억") : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/* ───── SVG 캔들차트 컴포넌트 ───── */
function CandleChart({ candles }: { candles: Candle[] }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; c: Candle } | null>(null);
  const [dims, setDims] = useState({ w: 800, h: 340 });

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const obs = new ResizeObserver(e => {
      setDims({ w: e[0].contentRect.width, h: e[0].contentRect.height });
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  if (!candles.length) return <div className={styles.noChartData}>데이터가 없습니다.</div>;

  const PAD = { t: 16, r: 12, b: 40, l: 68 };
  const W = dims.w - PAD.l - PAD.r;
  const H = dims.h - PAD.t - PAD.b;

  const valid = candles.filter(c => c.high != null && c.low != null);
  const priceMin = Math.min(...valid.map(c => c.low!));
  const priceMax = Math.max(...valid.map(c => c.high!));
  const pad = (priceMax - priceMin) * 0.05 || 1;
  const yMin = priceMin - pad;
  const yMax = priceMax + pad;

  const toY = (p: number) => PAD.t + H - ((p - yMin) / (yMax - yMin)) * H;
  const n = candles.length;
  const candleW = Math.max(1, Math.floor((W / n) * 0.7));
  const toX = (i: number) => PAD.l + (i + 0.5) * (W / n);

  // Y축 눈금
  const yTicks = 5;
  const yTickVals = Array.from({ length: yTicks }, (_, i) =>
    yMin + (i / (yTicks - 1)) * (yMax - yMin)
  );

  // X축 레이블 (날짜 간격 자동 조정)
  const step = Math.max(1, Math.floor(n / 8));
  const xLabels = candles
    .map((c, i) => ({ i, label: c.date.slice(0, 10) }))
    .filter((_, i) => i % step === 0);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <svg
        ref={svgRef}
        width="100%"
        height="100%"
        style={{ display: "block" }}
        onMouseLeave={() => setTooltip(null)}
      >
        {/* 그리드 */}
        {yTickVals.map((v, i) => (
          <g key={i}>
            <line
              x1={PAD.l} x2={PAD.l + W}
              y1={toY(v)} y2={toY(v)}
              stroke="rgba(255,255,255,0.05)" strokeWidth={1}
            />
            <text
              x={PAD.l - 6} y={toY(v) + 4}
              textAnchor="end" fill="#64748b" fontSize={10}
            >
              {v >= 1000 ? (v / 1000).toFixed(0) + "K" : v.toFixed(0)}
            </text>
          </g>
        ))}

        {/* X축 레이블 */}
        {xLabels.map(({ i, label }) => (
          <text key={i}
            x={toX(i)} y={PAD.t + H + 18}
            textAnchor="middle" fill="#64748b" fontSize={10}
          >{label.slice(5)}</text>
        ))}

        {/* 캔들 */}
        {candles.map((c, i) => {
          if (c.open == null || c.close == null || c.high == null || c.low == null) return null;
          const x = toX(i);
          const isUp = c.close >= c.open;
          const color = isUp ? "#ef4444" : "#3b82f6";
          const bodyTop = toY(Math.max(c.open, c.close));
          const bodyBot = toY(Math.min(c.open, c.close));
          const bodyH = Math.max(1, bodyBot - bodyTop);

          return (
            <g key={i}
              onMouseEnter={(e) => {
                const rect = svgRef.current!.getBoundingClientRect();
                setTooltip({ x: e.clientX - rect.left, y: e.clientY - rect.top, c });
              }}
            >
              {/* 심지 */}
              <line x1={x} x2={x} y1={toY(c.high)} y2={toY(c.low)}
                stroke={color} strokeWidth={1} />
              {/* 몸통 */}
              <rect
                x={x - candleW / 2} y={bodyTop}
                width={candleW} height={bodyH}
                fill={isUp ? color : "none"}
                stroke={color} strokeWidth={isUp ? 0 : 1.5}
              />
            </g>
          );
        })}
      </svg>

      {/* 툴팁 */}
      {tooltip && (
        <div style={{
          position: "absolute",
          left: Math.min(tooltip.x + 12, dims.w - 160),
          top: Math.max(8, tooltip.y - 60),
          background: "rgba(15,20,35,0.96)",
          border: "1px solid rgba(59,130,246,0.4)",
          borderRadius: 8,
          padding: "0.5rem 0.75rem",
          fontSize: "0.78rem",
          pointerEvents: "none",
          zIndex: 10,
          minWidth: 140,
        }}>
          <div style={{ color: "#94a3b8", marginBottom: 4, fontWeight: 600 }}>{tooltip.c.date}</div>
          {[
            ["시가", tooltip.c.open],
            ["고가", tooltip.c.high],
            ["저가", tooltip.c.low],
            ["종가", tooltip.c.close],
          ].map(([l, v]) => (
            <div key={l as string} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <span style={{ color: "#64748b" }}>{l}</span>
              <span style={{ color: "#e2e8f0", fontWeight: 600 }}>
                {v != null ? "₩" + (v as number).toLocaleString("ko-KR") : "-"}
              </span>
            </div>
          ))}
          {tooltip.c.volume != null && (
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 2 }}>
              <span style={{ color: "#64748b" }}>거래량</span>
              <span style={{ color: "#94a3b8" }}>{tooltip.c.volume.toLocaleString("ko-KR")}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ───── 메인 컴포넌트 ───── */
export default function ETFDetailPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const router = useRouter();

  const [detail, setDetail]         = useState<ETFDetail | null>(null);
  const [constituents, setConsts]   = useState<Constituent[]>([]);
  const [candles, setCandles]       = useState<Candle[]>([]);
  const [interval, setInterval]     = useState<Interval>("day");
  const [period, setPeriod]         = useState("1y");
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(false);
  const [showAllPort, setShowAll]   = useState(false);
  const [stockModal, setStockModal] = useState<{ ticker: string; name: string } | null>(null);

  // 상세 + 구성종목
  useEffect(() => {
    if (!ticker) return;
    setLoading(true); setError(false);
    Promise.all([
      fetch(`${API_BASE}/api/etfs/${ticker}`).then(r => { if (!r.ok) throw 0; return r.json(); }),
      fetch(`${API_BASE}/api/etfs/${ticker}/constituents`).then(r => r.json()).catch(() => []),
    ])
      .then(([d, c]) => { setDetail(d); setConsts(c); })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [ticker]);

  // 캔들 데이터
  const fetchCandles = useCallback((iv: Interval, p: string) => {
    if (!ticker) return;
    fetch(`${API_BASE}/api/etfs/${ticker}/history?period=${p}&interval=${iv}`)
      .then(r => r.json())
      .then(setCandles)
      .catch(() => setCandles([]));
  }, [ticker]);

  useEffect(() => { fetchCandles(interval, period); }, [fetchCandles, interval, period]);

  const INTERVALS: { key: Interval; label: string; periods: { key: string; label: string }[] }[] = [
    { key: "day",   label: "일봉", periods: [{ key:"1m", label:"1개월"}, { key:"3m", label:"3개월"}, { key:"6m", label:"6개월"}, { key:"1y", label:"1년"}] },
    { key: "week",  label: "주봉", periods: [{ key:"3m", label:"3개월"}, { key:"6m", label:"6개월"}, { key:"1y", label:"1년"}, { key:"5y", label:"5년"}] },
    { key: "month", label: "월봉", periods: [{ key:"1y", label:"1년"}, { key:"5y", label:"5년"}] },
    { key: "year",  label: "년봉", periods: [{ key:"5y", label:"5년"}] },
  ];

  const handleInterval = (iv: Interval) => {
    setInterval(iv);
    // 기본 기간 자동 세팅
    const defaultPeriod: Record<Interval, string> = { day: "1y", week: "1y", month: "1y", year: "5y" };
    setPeriod(defaultPeriod[iv]);
  };

  const currentIv = INTERVALS.find(x => x.key === interval)!;

  if (loading) return (
    <div className="dashboard-container">
      <div className={styles.loadingWrap}>
        <div className={styles.spinner} />
        <p style={{ color: "var(--text-secondary)" }}>데이터 로딩 중...</p>
      </div>
    </div>
  );

  if (error || !detail) return (
    <div className="dashboard-container">
      <button className={styles.backBtn} onClick={() => router.back()}>← 목록으로</button>
      <p style={{ color: "var(--text-secondary)" }}>종목을 찾을 수 없습니다.</p>
    </div>
  );

  const { text: changeText, cls: changeCls } = fmtR(detail.change_rate);
  const changeSign = (detail.change_rate ?? 0) >= 0 ? "+" : "";
  const portList = showAllPort ? constituents : constituents.slice(0, 15);
  const maxWeight = constituents[0]?.weight ?? 1;

  return (
    <div className="dashboard-container">
      <button className={styles.backBtn} onClick={() => router.back()}>← 목록으로</button>

      {/* ── 히어로 헤더 ── */}
      <div className={styles.heroSection}>
        <div className={styles.heroLeft}>
          <h1>{detail.name}</h1>
          <div className={styles.heroTicker}>{detail.ticker}</div>
          <div className={styles.badgeRow}>
            {detail.asset_type && <span className={`${styles.badge} ${styles.badgeAsset}`}>{detail.asset_type}</span>}
            {detail.region     && <span className={`${styles.badge} ${styles.badgeRegion}`}>{detail.region}</span>}
            {detail.sector     && <span className={`${styles.badge} ${styles.badgeSector}`}>{detail.sector}</span>}
            {detail.manager    && <span className={`${styles.badge} ${styles.badgeManager}`}>{detail.manager}</span>}
          </div>
        </div>
        <div className={styles.heroRight}>
          <div className={`${styles.currentPrice} ${changeCls}`}>{fmtP(detail.close)}</div>
          <div className={`${styles.priceChange} ${changeCls}`}>
            <span>{changeSign}{detail.change_val != null ? detail.change_val.toLocaleString("ko-KR") : "-"}원</span>
            <span>({changeText})</span>
          </div>
          <div className={styles.priceDate}>{detail.date ?? "-"} 기준</div>
        </div>
      </div>

      {/* ── 시세 정보 ── */}
      <div className={styles.quoteGrid}>
        {[
          ["전일 종가", fmtP(detail.prev_close), ""],
          ["시가",      fmtP(detail.open),       ""],
          ["고가",      fmtP(detail.high),        styles.positiveText],
          ["저가",      fmtP(detail.low),         styles.negativeText],
          ["거래량",    fmt(detail.volume,"주"),  ""],
          ["거래대금",  fmtTV(detail.trade_value),""],
        ].map(([label, value, cls]) => (
          <div key={label} className={styles.quoteCard}>
            <span className={styles.quoteLabel}>{label}</span>
            <span className={`${styles.quoteValue} ${cls}`}>{value}</span>
          </div>
        ))}
      </div>

      {/* ── 차트 + 투자정보 ── */}
      <div className={styles.midRow}>
        {/* 캔들차트 */}
        <div className={styles.chartPanel}>
          <div className={styles.chartHeader}>
            <div className={styles.panelTitle}>📊 캔들 차트</div>
            <div className={styles.chartControls}>
              {/* 봉 타입 */}
              <div className={styles.chartTabs}>
                {INTERVALS.map(({ key, label }) => (
                  <button key={key}
                    className={`${styles.chartTab} ${interval === key ? styles.chartTabActive : ""}`}
                    onClick={() => handleInterval(key)}
                  >{label}</button>
                ))}
              </div>
              {/* 기간 */}
              <div className={styles.chartTabs} style={{ marginLeft: "0.75rem" }}>
                {currentIv.periods.map(({ key, label }) => (
                  <button key={key}
                    className={`${styles.chartTab} ${period === key ? styles.chartTabActive : ""}`}
                    onClick={() => setPeriod(key)}
                  >{label}</button>
                ))}
              </div>
            </div>
          </div>
          <div className={styles.chartWrap}>
            <CandleChart candles={candles} />
          </div>
        </div>

        {/* 투자 정보 */}
        <div className={styles.infoPanel}>
          <div className={styles.panelTitle}>💼 투자 정보</div>
          <div className={styles.infoSectionTitle}>기본 정보</div>
          {[
            ["운용사", detail.manager ?? "-"],
            ["운용자산(AUM)", fmtMC(detail.market_cap)],
            ["배당수익률", "-"],
          ].map(([l, v]) => (
            <div key={l} className={styles.infoRow}>
              <span className={styles.infoLabel}>{l}</span>
              <span className={styles.infoValue}>{v}</span>
            </div>
          ))}
          <div className={styles.infoSectionTitle}>수익률</div>
          {(["1m","3m","6m","1y"] as const).map(p => {
            const labels = { "1m":"1개월","3m":"3개월","6m":"6개월","1y":"1년" };
            const vals   = { "1m":detail.return_1m,"3m":detail.return_3m,"6m":detail.return_6m,"1y":detail.return_1y };
            const { text, cls } = fmtR(vals[p]);
            return (
              <div key={p} className={styles.infoRow}>
                <span className={styles.infoLabel}>{labels[p]} 수익률</span>
                <span className={`${styles.infoValue} ${cls}`}>{text}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── 포트폴리오 ── */}
      <div className={styles.portfolioPanel}>
        <div className={styles.panelTitle}>
          📋 포트폴리오 구성종목
          {constituents.length > 0 && (
            <span style={{ fontSize:"0.78rem", fontWeight:400, color:"var(--text-secondary)", marginLeft:"0.4rem" }}>
              총 {constituents.length}종목
            </span>
          )}
        </div>
        {constituents.length === 0 ? (
          <div className={styles.emptyPortfolio}>구성종목 데이터가 없습니다.</div>
        ) : (
          <>
            <div style={{ overflowX:"auto" }}>
              <table className={styles.portfolioTable}>
                <thead><tr>
                  <th style={{ width:36 }}>#</th>
                  <th>종목명</th><th>티커</th>
                  <th style={{ textAlign:"right" }}>구성률</th>
                </tr></thead>
                <tbody>
                  {portList.map((c, i) => {
                    const bw = c.weight != null && maxWeight > 0 ? Math.max(2, Math.round((c.weight / maxWeight) * 80)) : 2;
                    return (
                      <tr key={c.stock_ticker + i}
                        className={styles.tableRowHover}
                        style={{ cursor: "pointer" }}
                        onClick={() => setStockModal({ ticker: c.stock_ticker, name: c.stock_name })}
                        title="클릭하면 이 종목을 포함한 ETF 목록을 볼 수 있습니다"
                      >
                        <td className={styles.rankNum}>{i + 1}</td>
                        <td style={{ fontWeight:500 }}>
                          {c.stock_name}
                          <span style={{ marginLeft:"0.3rem", fontSize:"0.7rem", color:"#3b82f6", opacity:0.7 }}>↗</span>
                        </td>
                        <td style={{ color:"var(--text-secondary)", fontSize:"0.78rem" }}>{c.stock_ticker}</td>
                        <td>
                          <div style={{ display:"flex", alignItems:"center", justifyContent:"flex-end", gap:"0.4rem" }}>
                            <span className={styles.weightBar} style={{ width: bw }} />
                            <span className={styles.weightText}>{c.weight != null ? c.weight.toFixed(2)+"%" : "-"}</span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {constituents.length > 15 && (
              <button onClick={() => setShowAll(v => !v)} style={{
                marginTop:"0.75rem", width:"100%", padding:"0.5rem",
                background:"rgba(255,255,255,0.04)", border:"1px solid rgba(255,255,255,0.08)",
                borderRadius:8, color:"var(--text-secondary)", fontSize:"0.82rem",
                cursor:"pointer", transition:"all 0.15s",
              }}>
                {showAllPort ? "▲ 접기" : `▼ 전체보기 (${constituents.length - 15}개 더)`}
              </button>
            )}
          </>
        )}
      </div>

      {/* ── 종목 → ETF 목록 모달 ── */}
      {stockModal && (
        <StockEtfModal
          stock={stockModal}
          onClose={() => setStockModal(null)}
          onEtfClick={(etfTicker) => {
            setStockModal(null);
            router.push(`/etf/${etfTicker}`);
          }}
        />
      )}
    </div>
  );
}
