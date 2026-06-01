"""
GemHunter — Streamlit Web App
Birbaşa brauzerdə işləyir. Terminal lazım deyil.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone
import time

from modules.scanner import LowCapScanner
from modules.social_detector import SocialHypeDetector
from modules.whale_tracker import WhaleAccumulationTracker
from modules.gem_scorer import GemScorer
from utils.config import GemConfig

# ── Səhifə konfiqurasiyası ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="💎 GemHunter",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0a0e1a; }
    .stApp { background-color: #0a0e1a; }
    
    div[data-testid="metric-container"] {
        background: #111827;
        border: 1px solid #1f2937;
        border-radius: 10px;
        padding: 14px 18px;
    }
    div[data-testid="metric-container"] label { color: #6b7280 !important; font-size: 12px; }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #f3f4f6 !important; font-size: 26px; font-weight: 600;
    }

    .gem-card {
        background: #111827;
        border: 1px solid #1f2937;
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 10px;
    }
    .tier-moonshot   { color: #fbbf24; font-weight: 700; font-size: 12px; }
    .tier-high       { color: #4ade80; font-weight: 700; font-size: 12px; }
    .tier-watch      { color: #60a5fa; font-weight: 700; font-size: 12px; }
    .tier-spec       { color: #a78bfa; font-weight: 700; font-size: 12px; }
    .tier-avoid      { color: #6b7280; font-weight: 700; font-size: 12px; }
    .alert-tag {
        display: inline-block;
        background: rgba(245,158,11,0.15);
        color: #fbbf24;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 11px;
        margin-right: 4px;
    }
    .score-big {
        font-size: 32px;
        font-weight: 700;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] { background: #0d1117; border-right: 1px solid #1f2937; }
    section[data-testid="stSidebar"] .stSlider label { color: #9ca3af; }

    /* Buttons */
    .stButton > button {
        background: #1f2937;
        color: #f3f4f6;
        border: 1px solid #374151;
        border-radius: 8px;
        width: 100%;
        padding: 10px;
        font-size: 14px;
        font-weight: 600;
    }
    .stButton > button:hover { background: #374151; border-color: #4b5563; }

    h1, h2, h3 { color: #f3f4f6 !important; }
    p, span, div { color: #d1d5db; }
    
    .stDataFrame { background: #111827; }
    div[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)


# ── Sidebar — parametrlər ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 💎 GemHunter")
    st.markdown("---")

    st.markdown("### 🔍 Scan Parametrləri")

    mcap_range = st.slider(
        "Market Cap aralığı ($M)",
        min_value=1, max_value=200,
        value=(5, 50), step=1,
    )

    max_price = st.slider(
        "Maksimum qiymət ($)",
        min_value=0.01, max_value=10.0,
        value=1.0, step=0.01,
        format="$%.2f",
    )

    universe_size = st.select_slider(
        "Neçə coin tara?",
        options=[100, 250, 500, 750, 1000],
        value=250,
    )

    top_n = st.slider("Top neçə göstər?", 5, 20, 10)

    st.markdown("---")
    st.markdown("### ⚙️ Modullar")
    use_social = st.toggle("Sosial analiz", value=True)
    use_whale  = st.toggle("Whale tracker", value=True)

    st.markdown("---")

    run_btn = st.button("🚀 Scan et!", use_container_width=True)

    st.markdown("---")
    st.markdown("### 📊 Xal sistemi")
    st.markdown("""
    | Ölçü | Maks |
    |------|------|
    | 🏷️ Low-Cap | 3 xal |
    | 📢 Social  | 4 xal |
    | 🐋 Whale   | 3 xal |
    | **TOPLAM** | **10 xal** |
    """)

    st.markdown("---")
    st.caption("Data: CoinGecko API · Pulsuz")


# ── Başlıq ─────────────────────────────────────────────────────────────────────
col_title, col_time = st.columns([3, 1])
with col_title:
    st.markdown("# 💎 GemHunter — Low-Cap Alpha Scanner")
    st.markdown("Micro-cap coinlər arasında partlayış potensialı olanları tapır")
with col_time:
    st.markdown(f"<br><small style='color:#4b5563'>Son yenilənmə:<br>{datetime.now(timezone.utc).strftime('%H:%M UTC')}</small>", unsafe_allow_html=True)

st.markdown("---")


# ── Scan funksiyası (cache ilə) ────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)   # 5 dəq cache
def run_scan(mcap_min, mcap_max, max_price, universe, do_social, do_whale):
    config = GemConfig(
        max_price     = max_price,
        mcap_min      = mcap_min * 1_000_000,
        mcap_max      = mcap_max * 1_000_000,
        scan_universe = universe,
    )

    scanner = LowCapScanner(config)
    coins   = scanner.scan()
    if not coins:
        return []

    coins = coins[:min(len(coins), 30)]  # API limit üçün

    if do_social:
        social = SocialHypeDetector(config)
        social.analyse_batch(coins)

    if do_whale:
        whale = WhaleAccumulationTracker(config)
        whale.analyse_batch(coins)

    scorer = GemScorer(config)
    coins  = scorer.score_all(coins)
    return coins


# ── Session state ──────────────────────────────────────────────────────────────
if "coins" not in st.session_state:
    st.session_state.coins = []
if "scanned" not in st.session_state:
    st.session_state.scanned = False


# ── Scan düyməsi basıldıqda ────────────────────────────────────────────────────
if run_btn:
    with st.spinner("🔍 CoinGecko-dan data çəkilir..."):
        progress = st.progress(0, text="Scanner başladılır...")
        time.sleep(0.3)
        progress.progress(15, text="Low-cap coinlər süzülür...")

        try:
            coins = run_scan(
                mcap_min   = mcap_range[0],
                mcap_max   = mcap_range[1],
                max_price  = max_price,
                universe   = universe_size,
                do_social  = use_social,
                do_whale   = use_whale,
            )
            progress.progress(80, text="Xallar hesablanır...")
            time.sleep(0.3)
            progress.progress(100, text="Hazır!")
            time.sleep(0.3)
            progress.empty()

            st.session_state.coins   = coins
            st.session_state.scanned = True

            if coins:
                st.success(f"✅ {len(coins)} coin tapıldı! Top {top_n} aşağıda göstərilir.")
            else:
                st.warning("⚠️ Heç bir coin filter-dən keçmədi. Parametrləri genişləndir.")

        except Exception as e:
            progress.empty()
            st.error(f"❌ Xəta baş verdi: {e}")
            st.info("CoinGecko pulsuz API-nin rate limiti var. 1-2 dəqiqə gözləyib yenidən cəhd edin.")


# ── Nəticə göstərilməsi ────────────────────────────────────────────────────────
if st.session_state.scanned and st.session_state.coins:
    coins = st.session_state.coins
    top   = coins[:top_n]

    # ── Ümumi statistika ───────────────────────────────────────────────────────
    total_coins   = len(coins)
    moonshots     = sum(1 for c in coins if c.get("scores", {}).get("tier") == "MOONSHOT")
    social_spikes = sum(1 for c in coins if c.get("social", {}).get("social_spike"))
    whale_flags   = sum(1 for c in coins if c.get("whale", {}).get("vol_spike"))
    avg_score     = sum(c.get("scores", {}).get("gem_score", 0) for c in coins) / max(len(coins), 1)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("💎 Tapılan gem", total_coins)
    m2.metric("🌙 Moonshot",    moonshots)
    m3.metric("📢 Sosial spike", social_spikes)
    m4.metric("🐋 Whale flag",  whale_flags)
    m5.metric("📊 Ort. xal",    f"{avg_score:.1f}/10")

    st.markdown("---")

    # ── Tab-lar ────────────────────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["🏆 Top Gems", "📊 Qrafiklər", "📋 Bütün data"])

    # ── Tab 1: Gem kartları ────────────────────────────────────────────────────
    with tab1:
        TIER_CSS = {
            "MOONSHOT":        "tier-moonshot",
            "HIGH CONVICTION": "tier-high",
            "WATCHLIST":       "tier-watch",
            "SPECULATIVE":     "tier-spec",
            "AVOID":           "tier-avoid",
        }
        TIER_EMOJI = {
            "MOONSHOT": "🌙", "HIGH CONVICTION": "🟢",
            "WATCHLIST": "🔵", "SPECULATIVE": "🟣", "AVOID": "⚫",
        }
        SCORE_COLOR = lambda s: "#fbbf24" if s >= 8 else "#4ade80" if s >= 6.5 else "#60a5fa" if s >= 5 else "#a78bfa"

        medals = ["🥇","🥈","🥉"]

        for i, coin in enumerate(top):
            sc     = coin.get("scores", {})
            soc    = coin.get("social", {})
            wh     = coin.get("whale",  {})
            score  = sc.get("gem_score", 0)
            tier   = sc.get("tier", "AVOID")
            alerts = sc.get("alerts", [])

            price  = coin.get("price") or 0
            mcap   = coin.get("mcap")  or 0
            chg    = coin.get("chg_24h") or 0
            pstr   = f"${price:.6f}" if price < 0.001 else f"${price:.4f}" if price < 0.1 else f"${price:.3f}"
            mstr   = f"${mcap/1e6:.1f}M"
            chg_col = "green" if chg > 0 else "red"
            chg_str = f"+{chg:.1f}%" if chg > 0 else f"{chg:.1f}%"
            medal   = medals[i] if i < 3 else f"#{i+1}"

            col_main, col_score = st.columns([4, 1])

            with col_main:
                st.markdown(f"""
                <div class="gem-card">
                    <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">
                        <span style="font-size:22px">{medal}</span>
                        <div>
                            <span style="font-size:18px;font-weight:700;color:#f3f4f6">{coin['symbol']}</span>
                            <span style="font-size:13px;color:#6b7280;margin-left:8px">{coin['name']}</span>
                            <span class="{TIER_CSS.get(tier,'tier-avoid')}" style="margin-left:12px">
                                {TIER_EMOJI.get(tier,'')} {tier}
                            </span>
                        </div>
                        <div style="margin-left:auto;text-align:right">
                            <span style="font-size:15px;font-weight:600;color:#f3f4f6">{pstr}</span>
                            <span style="font-size:12px;color:{chg_col};margin-left:8px">{chg_str}</span>
                            <br><span style="font-size:12px;color:#6b7280">MCap: {mstr}</span>
                        </div>
                    </div>
                    <div style="display:flex;gap:6px;margin-bottom:10px">
                        {"".join(f'<span class="alert-tag">⚡ {a}</span>' for a in alerts[:4])}
                    </div>
                    <div style="display:flex;gap:20px">
                        <div><span style="color:#8b5cf6;font-size:12px">🏷️ Low-Cap</span><br>
                             <span style="font-size:18px;font-weight:600;color:#8b5cf6">{sc.get('lowcap_score',0):.1f}</span><span style="color:#6b7280;font-size:11px">/3</span></div>
                        <div><span style="color:#38bdf8;font-size:12px">📢 Social</span><br>
                             <span style="font-size:18px;font-weight:600;color:#38bdf8">{sc.get('social_score',0):.1f}</span><span style="color:#6b7280;font-size:11px">/4</span></div>
                        <div><span style="color:#10b981;font-size:12px">🐋 Whale</span><br>
                             <span style="font-size:18px;font-weight:600;color:#10b981">{sc.get('whale_score',0):.1f}</span><span style="color:#6b7280;font-size:11px">/3</span></div>
                        <div style="margin-left:20px">
                             <span style="color:#9ca3af;font-size:12px">Vol/MCap</span><br>
                             <span style="font-size:15px;color:#f3f4f6">{wh.get('vol_mcap_ratio',0):.0%}</span></div>
                        <div><span style="color:#9ca3af;font-size:12px">Vol trend</span><br>
                             <span style="font-size:15px;color:#f3f4f6">{wh.get('vol_trend','—')}</span></div>
                        <div><span style="color:#9ca3af;font-size:12px">Trending</span><br>
                             <span style="font-size:15px;color:#fbbf24">{"#"+str(soc.get('trending_rank')) if soc.get('trending_rank') else "—"}</span></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            with col_score:
                st.markdown(f"""
                <div style="text-align:center;padding:20px 10px;background:#111827;
                            border:1px solid #1f2937;border-radius:12px;height:100%">
                    <div style="font-size:11px;color:#6b7280;margin-bottom:4px">GEM SCORE</div>
                    <div class="score-big" style="color:{SCORE_COLOR(score)}">{score:.2f}</div>
                    <div style="font-size:11px;color:#4b5563">/ 10</div>
                </div>
                """, unsafe_allow_html=True)

    # ── Tab 2: Qrafiklər ───────────────────────────────────────────────────────
    with tab2:
        chart_data = []
        for c in top:
            sc = c.get("scores", {})
            wh = c.get("whale",  {})
            so = c.get("social", {})
            chart_data.append({
                "Symbol":     c["symbol"],
                "Gem Score":  sc.get("gem_score",    0),
                "Low-Cap":    sc.get("lowcap_score",  0),
                "Social":     sc.get("social_score",  0),
                "Whale":      sc.get("whale_score",   0),
                "Vol/MCap %": round(wh.get("vol_mcap_ratio", 0) * 100, 1),
                "Hype Score": round(so.get("hype_score", 0), 3),
                "Tier":       sc.get("tier", "AVOID"),
                "MCap $M":    round((c.get("mcap") or 0) / 1e6, 1),
            })
        df = pd.DataFrame(chart_data)

        TIER_COLOR_MAP = {
            "MOONSHOT":"#fbbf24","HIGH CONVICTION":"#4ade80",
            "WATCHLIST":"#60a5fa","SPECULATIVE":"#a78bfa","AVOID":"#6b7280",
        }

        c1, c2 = st.columns(2)

        with c1:
            st.markdown("#### Xal dağılımı (stacked)")
            fig = go.Figure()
            fig.add_trace(go.Bar(name="Low-Cap", x=df["Symbol"], y=df["Low-Cap"],  marker_color="#8b5cf6"))
            fig.add_trace(go.Bar(name="Social",  x=df["Symbol"], y=df["Social"],   marker_color="#38bdf8"))
            fig.add_trace(go.Bar(name="Whale",   x=df["Symbol"], y=df["Whale"],    marker_color="#10b981"))
            fig.update_layout(
                barmode="stack", height=320,
                paper_bgcolor="#111827", plot_bgcolor="#111827",
                font=dict(color="#9ca3af"),
                legend=dict(bgcolor="#111827"),
                margin=dict(l=20,r=20,t=20,b=40),
                yaxis=dict(range=[0,10], gridcolor="#1f2937"),
                xaxis=dict(gridcolor="#1f2937"),
            )
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.markdown("#### Vol/MCap vs Hype (baloncuq = gem score)")
            fig2 = px.scatter(
                df, x="Vol/MCap %", y="Hype Score",
                size="Gem Score", color="Tier",
                text="Symbol",
                color_discrete_map=TIER_COLOR_MAP,
                size_max=40, height=320,
            )
            fig2.update_traces(textposition="top center", textfont=dict(size=10, color="#e2e8f0"))
            fig2.update_layout(
                paper_bgcolor="#111827", plot_bgcolor="#111827",
                font=dict(color="#9ca3af"),
                legend=dict(bgcolor="#111827"),
                margin=dict(l=20,r=20,t=20,b=40),
                xaxis=dict(gridcolor="#1f2937"),
                yaxis=dict(gridcolor="#1f2937"),
            )
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### Gem score sıralama")
        fig3 = px.bar(
            df.sort_values("Gem Score"),
            x="Gem Score", y="Symbol",
            orientation="h",
            color="Tier",
            color_discrete_map=TIER_COLOR_MAP,
            height=max(300, len(df) * 36),
            text="Gem Score",
        )
        fig3.update_traces(texttemplate="%{text:.2f}", textposition="outside")
        fig3.update_layout(
            paper_bgcolor="#111827", plot_bgcolor="#111827",
            font=dict(color="#9ca3af"),
            legend=dict(bgcolor="#111827"),
            margin=dict(l=20,r=20,t=20,b=40),
            xaxis=dict(range=[0,11], gridcolor="#1f2937"),
            yaxis=dict(gridcolor="#1f2937"),
        )
        st.plotly_chart(fig3, use_container_width=True)

    # ── Tab 3: Tam cədvəl ──────────────────────────────────────────────────────
    with tab3:
        rows = []
        for c in coins:
            sc = c.get("scores", {})
            wh = c.get("whale",  {})
            so = c.get("social", {})
            rows.append({
                "Symbol":     c["symbol"],
                "Ad":         c["name"],
                "Qiymət":     c.get("price"),
                "MCap ($M)":  round((c.get("mcap") or 0)/1e6, 2),
                "24h %":      round(c.get("chg_24h") or 0, 2),
                "Low-Cap":    sc.get("lowcap_score", 0),
                "Social":     sc.get("social_score", 0),
                "Whale":      sc.get("whale_score",  0),
                "Gem Score":  sc.get("gem_score",    0),
                "Tier":       sc.get("tier",         ""),
                "Vol/MCap":   f"{wh.get('vol_mcap_ratio',0):.0%}",
                "Trending":   so.get("trending_rank"),
                "Spike":      "✅" if so.get("social_spike") else "",
                "Xəbərdarlıq": " | ".join(sc.get("alerts", [])[:2]),
            })
        full_df = pd.DataFrame(rows)
        st.dataframe(
            full_df,
            use_container_width=True,
            height=500,
            column_config={
                "Gem Score": st.column_config.ProgressColumn("Gem Score", min_value=0, max_value=10),
                "Qiymət":    st.column_config.NumberColumn("Qiymət", format="$%.6f"),
            }
        )

        csv = full_df.to_csv(index=False)
        st.download_button("⬇️ CSV yüklə", csv, "gemhunter_results.csv", "text/csv")

# ── Hələ scan edilməyibsə ──────────────────────────────────────────────────────
else:
    st.markdown("""
    <div style="text-align:center;padding:80px 20px">
        <div style="font-size:64px;margin-bottom:20px">💎</div>
        <h2 style="color:#f3f4f6">GemHunter-ə xoş gəlmisiniz</h2>
        <p style="color:#6b7280;font-size:16px;max-width:500px;margin:0 auto">
            Sol paneldən parametrləri seçin və <strong style="color:#38bdf8">🚀 Scan et!</strong> düyməsinə basın.<br><br>
            Proqram CoinGecko-dan real data çəkəcək, sosial hype və whale
            akkumulyasiya siqnallarını analiz edəcək.
        </p>
        <br>
        <div style="display:inline-flex;gap:30px;color:#4b5563;font-size:13px">
            <span>🆓 Pulsuz API</span>
            <span>⏱️ ~2-3 dəqiqə</span>
            <span>🔄 5 dəq cache</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
