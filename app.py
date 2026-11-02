"""Instagram Performance Analytics for Sugar Cosmetics — Streamlit dashboard."""
import os
import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ----------------------------------------------------------------------------
# Config & style
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Sugar Cosmetics · Instagram Analytics",
                   page_icon="💄", layout="wide")

PINK, DARK, GREY = "#D81B60", "#1F1F2E", "#9AA0A6"
PALETTE = ["#D81B60", "#1F1F2E", "#F48FB1", "#6C63FF", "#FFB300", "#26A69A"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DATA_PATH = Path(__file__).parent / "data" / "sugar_cosmetics_instagram_data.csv"

# Background colours (change these to restyle the whole app)
BG_MAIN = "#FDE7EF"     # main page background (soft blush pink)
BG_SIDEBAR = "#F9CFDF"  # sidebar background

st.markdown(f"""
<style>
.stApp {{background-color:{BG_MAIN};}}
section[data-testid="stSidebar"] {{background-color:{BG_SIDEBAR};}}
header[data-testid="stHeader"] {{background:transparent;}}
.block-container {{padding-top: 1.5rem;}}
div[data-testid="stMetric"] {{background:#fff;border:1px solid #eee;border-left:5px solid {PINK};
  padding:12px 16px;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.05);}}
div[data-testid="stMetricLabel"] p {{font-size:.8rem;color:#666;text-transform:uppercase;letter-spacing:.04em;}}
.hero {{background:linear-gradient(90deg,{DARK},{PINK});color:#fff;padding:22px 28px;border-radius:14px;margin-bottom:14px;}}
.hero h1 {{margin:0;font-size:1.9rem;color:#fff;}} .hero p {{margin:4px 0 0;opacity:.9;}}
.insight {{background:#FFFFFF;border-left:4px solid {PINK};padding:10px 14px;border-radius:6px;margin:6px 0;}}
</style>""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading data…")
def load_data(source) -> pd.DataFrame:
    df = pd.read_excel(source) if str(getattr(source, "name", source)).endswith("xlsx") else pd.read_csv(source)
    df.columns = [c.strip().replace(" ", "_") for c in df.columns]
    df["Post_Date"] = pd.to_datetime(df["Post_Date"])
    df = df.drop_duplicates().dropna(subset=["Post_Date", "Reach"])
    df = df[df["Reach"] > 0].reset_index(drop=True)
    df["Post_ID"] = df.index + 1
    df["Engagements"] = df[["Likes", "Comments", "Shares", "Saves"]].sum(axis=1)
    df["ER"] = df["Engagements"] / df["Reach"] * 100                      # engagement rate %
    df["Follow_Conv"] = df["Follows"] / df["Profile_Visits"].replace(0, pd.NA) * 100
    df["Month"] = df["Post_Date"].dt.to_period("M").dt.to_timestamp()
    df["Weekday"] = pd.Categorical(df["Post_Date"].dt.day_name(), DAYS, ordered=True)
    df["Label"] = ("#" + df["Post_ID"].astype(str) + " · " + df["Post_Date"].dt.strftime("%d %b %y")
                   + " · " + df["Post_Type"] + " · " + df["Campaign_Type"])
    return df


uploaded = st.sidebar.file_uploader("Upload your own data (optional)", type=["csv", "xlsx"])
src = uploaded if uploaded else DATA_PATH
if not uploaded and not DATA_PATH.exists():
    st.error("Dataset not found. Put the CSV in /data or upload it from the sidebar.")
    st.stop()
raw = load_data(src)

# ----------------------------------------------------------------------------
# Sidebar filters
# ----------------------------------------------------------------------------
st.sidebar.header("🔎 Filters")
dmin, dmax = raw["Post_Date"].min().date(), raw["Post_Date"].max().date()
dates = st.sidebar.date_input("Date range", (dmin, dmax), min_value=dmin, max_value=dmax)
if len(dates) != 2:
    st.stop()


def multi(label, col):
    opts = sorted(raw[col].unique())
    return st.sidebar.multiselect(label, opts, default=opts)


f_type = multi("Post type", "Post_Type")
f_camp = multi("Campaign type", "Campaign_Type")
f_src = multi("Engagement source", "Engagement_Source")
f_emo = multi("Audience emotion", "Audience_Emotion")
all_tags = sorted({t for s in raw["Hashtags"] for t in s.split(", ")})
f_tag = st.sidebar.multiselect("Hashtag (posts containing any)", all_tags, default=all_tags)


def apply(df, start, end):
    m = (df["Post_Date"].dt.date.between(start, end) & df["Post_Type"].isin(f_type)
         & df["Campaign_Type"].isin(f_camp) & df["Engagement_Source"].isin(f_src)
         & df["Audience_Emotion"].isin(f_emo))
    if f_tag and len(f_tag) < len(all_tags):
        m &= df["Hashtags"].str.contains("|".join(map(re.escape, f_tag)))
    return df[m]


df = apply(raw, *dates)
span = (dates[1] - dates[0]).days + 1
prev = apply(raw, dates[0] - pd.Timedelta(days=span), dates[0] - pd.Timedelta(days=1))

if df.empty:
    st.warning("No posts match the selected filters.")
    st.stop()

st.sidebar.caption(f"{len(df):,} of {len(raw):,} posts selected")
st.sidebar.download_button("⬇️ Download filtered data", df.to_csv(index=False).encode(),
                           "filtered_instagram_data.csv", "text/csv")

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def secret(name, default=None):
    try:
        return st.secrets[name]
    except Exception:  # no secrets.toml or key missing
        return os.getenv(name, default)


def fmt(n):
    return f"{n/1e6:.2f}M" if n >= 1e6 else f"{n/1e3:.1f}K" if n >= 1e4 else f"{n:,.0f}"


def delta(cur, old, pct=True):
    if prev.empty or not old:
        return None
    return f"{(cur/old-1)*100:+.1f}% vs prev. period" if pct else f"{cur-old:+.2f} pp vs prev. period"


def style(fig, h=380):
    fig.update_layout(template="plotly_white", height=h, margin=dict(l=10, r=10, t=50, b=10),
                      title_font_size=16, legend_title_text="", colorway=PALETTE,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def lift_chart(frame, col, title, order=None):
    g = frame.groupby(col, observed=True)["ER"].mean()
    lift = ((g / frame["ER"].mean() - 1) * 100).reset_index(name="Lift")
    fig = px.bar(lift, x=col, y="Lift", text=lift["Lift"].map("{:+.2f}%".format), title=title,
                 color="Lift", color_continuous_scale=["#9AA0A6", "#F8BBD0", PINK],
                 category_orders={col: order} if order else None)
    fig.update_traces(textposition="outside")
    fig.update_layout(coloraxis_showscale=False, yaxis_title="Engagement-rate lift vs overall avg (%)")
    return style(fig)


def spread(frame, col):
    g = frame.groupby(col, observed=True)["ER"].mean().sort_values(ascending=False)
    return g.index[0], g.iloc[0], g.index[-1], g.iloc[-1], (g.iloc[0] / g.iloc[-1] - 1) * 100


# ----------------------------------------------------------------------------
# Header — Instagram logo + dashboard title
# ----------------------------------------------------------------------------
st.markdown(f"""
<div class="hero" style="display:flex;align-items:center;gap:16px;">
  <div style="flex:0 0 58px;width:58px;height:58px;background:#fff;border-radius:16px;
              display:flex;align-items:center;justify-content:center;">
    <svg width="42" height="42" viewBox="0 0 48 48" role="img" aria-label="Instagram logo"
         xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="instagramGradient" x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#FFDC80"/>
          <stop offset="35%" stop-color="#F77737"/>
          <stop offset="65%" stop-color="#E1306C"/>
          <stop offset="100%" stop-color="#833AB4"/>
        </linearGradient>
      </defs>
      <rect x="4" y="4" width="40" height="40" rx="12" fill="url(#instagramGradient)"/>
      <rect x="12" y="12" width="24" height="24" rx="7" fill="none" stroke="#fff" stroke-width="3"/>
      <circle cx="24" cy="24" r="6" fill="none" stroke="#fff" stroke-width="3"/>
      <circle cx="32" cy="16" r="2" fill="#fff"/>
    </svg>
  </div>
  <div>
    <h1 style="margin:0;font-size:1.9rem;color:#fff;">Sugar Cosmetics · Instagram Performance Analytics</h1>
    <p style="margin:4px 0 0;opacity:.9;">{dates[0]:%d %b %Y} → {dates[1]:%d %b %Y} &nbsp;|&nbsp; {len(df):,} posts &nbsp;|&nbsp;
    Engagement rate = (likes + comments + shares + saves) ÷ reach</p>
  </div>
</div>""", unsafe_allow_html=True)

tabs = st.tabs(["📊 Overview", "📈 Trends", "🎬 Content", "🕒 Timing", "🔻 Funnel",
                "#️⃣ Hashtags", "👥 Audience & Growth", "🏆 Top Posts", "💡 Insights & AI"])

# ------------------------------- Overview ------------------------------------
with tabs[0]:
    c = st.columns(5)
    c[0].metric("Total posts", f"{len(df):,}", delta(len(df), len(prev)))
    c[1].metric("Total likes", fmt(df.Likes.sum()), delta(df.Likes.sum(), prev.Likes.sum()))
    c[2].metric("Total comments", fmt(df.Comments.sum()), delta(df.Comments.sum(), prev.Comments.sum()))
    c[3].metric("Total reach", fmt(df.Reach.sum()), delta(df.Reach.sum(), prev.Reach.sum()))
    c[4].metric("Avg engagement rate", f"{df.ER.mean():.2f}%",
                delta(df.ER.mean(), prev.ER.mean() if not prev.empty else 0, pct=False))
    c = st.columns(5)
    c[0].metric("Impressions", fmt(df.Impressions.sum()))
    c[1].metric("Shares", fmt(df.Shares.sum()))
    c[2].metric("Saves", fmt(df.Saves.sum()))
    c[3].metric("New follows", fmt(df.Follows.sum()))
    c[4].metric("Profile visit → follow", f"{df.Follows.sum()/df.Profile_Visits.sum()*100:.1f}%")

    m = df.groupby("Month").agg(Reach=("Reach", "sum"), Engagements=("Engagements", "sum")).reset_index()
    fig = go.Figure()
    fig.add_bar(x=m.Month, y=m.Reach, name="Reach", marker_color="#F8BBD0")
    fig.add_scatter(x=m.Month, y=m.Engagements, name="Engagements", yaxis="y2",
                    line=dict(color=PINK, width=3), mode="lines+markers")
    fig.update_layout(title="Reach vs engagements by month",
                      yaxis2=dict(overlaying="y", side="right", showgrid=False))
    st.plotly_chart(style(fig, 360), width="stretch")
    st.caption("ℹ️ Apr-2024 and Apr-2025 are partial months (data runs 19 Apr 2024 → 19 Apr 2025).")

# ------------------------------- Trends --------------------------------------
with tabs[1]:
    m = df.groupby("Month").agg(Posts=("Post_ID", "count"), ER=("ER", "mean"),
                                Follows=("Follows", "sum")).reset_index()
    c1, c2 = st.columns(2)
    fig = px.line(m, x="Month", y="Posts", markers=True, title="Posts per month")
    fig.update_traces(line_color=PINK)
    c1.plotly_chart(style(fig), width="stretch")
    fig = px.line(m, x="Month", y="ER", markers=True, title="Average engagement rate by month (%)")
    fig.update_traces(line_color=DARK)
    c2.plotly_chart(style(fig), width="stretch")
    t = df.groupby(["Month", "Post_Type"]).size().reset_index(name="Posts")
    fig = px.area(t, x="Month", y="Posts", color="Post_Type", title="Content mix over time")
    st.plotly_chart(style(fig), width="stretch")

# ------------------------------- Content -------------------------------------
with tabs[2]:
    g = df.groupby("Post_Type").agg(Likes=("Likes", "mean"), Comments=("Comments", "mean"),
                                    Saves=("Saves", "mean"), ER=("ER", "mean")).reset_index()
    long = g.melt("Post_Type", ["Likes", "Comments", "Saves"], "Metric", "Average")
    fig = px.bar(long, x="Post_Type", y="Average", color="Post_Type", facet_col="Metric",
                 text_auto=".0f", title="Average likes, comments & saves per post type")
    fig.update_yaxes(matches=None, showticklabels=True)
    fig.update_xaxes(title="")
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    st.plotly_chart(style(fig, 400), width="stretch")
    c1, c2 = st.columns(2)
    c1.plotly_chart(lift_chart(df, "Post_Type", "Engagement-rate lift by post type"), width="stretch")
    c2.plotly_chart(lift_chart(df, "Campaign_Type", "Engagement-rate lift by campaign type"),
                    width="stretch")
    h = df.pivot_table(index="Campaign_Type", columns="Post_Type", values="ER", aggfunc="mean")
    fig = px.imshow(h, text_auto=".2f", aspect="auto", color_continuous_scale="RdPu",
                    title="Avg engagement rate (%) · campaign × post type")
    st.plotly_chart(style(fig, 360), width="stretch")

# ------------------------------- Timing --------------------------------------
with tabs[3]:
    c1, c2 = st.columns(2)
    wd = df.groupby("Weekday", observed=True).agg(ER=("ER", "mean"), Posts=("Post_ID", "count")).reset_index()
    fig = px.bar(wd, x="Weekday", y="ER", text=wd.ER.map("{:.2f}%".format), title="Avg engagement rate by weekday")
    fig.update_traces(marker_color=PINK, textposition="outside")
    c1.plotly_chart(style(fig), width="stretch")
    c2.plotly_chart(lift_chart(df, "Weekday", "Weekday lift vs overall average", DAYS), width="stretch")
    h = df.pivot_table(index="Weekday", columns="Post_Type", values="ER", aggfunc="mean", observed=True)
    fig = px.imshow(h, text_auto=".2f", aspect="auto", color_continuous_scale="RdPu",
                    title="Avg engagement rate (%) · weekday × post type")
    st.plotly_chart(style(fig, 400), width="stretch")
    st.caption("The lift chart zooms in on the differences, which are small in absolute terms — read it with the bar chart.")

# ------------------------------- Funnel --------------------------------------
with tabs[4]:
    stages = ["Impressions", "Reach", "Likes", "Comments", "Shares", "Saves"]
    vals = [df[s].sum() for s in stages]
    fig = go.Figure(go.Funnel(y=stages, x=vals, textinfo="value+percent previous",
                              marker=dict(color=PALETTE)))
    fig.update_layout(title="Engagement funnel: Impressions → Reach → Likes → Comments → Shares → Saves")
    st.plotly_chart(style(fig, 480), width="stretch")
    c = st.columns(4)
    c[0].metric("Reach / impressions", f"{vals[1]/vals[0]*100:.1f}%")
    c[1].metric("Likes / reach", f"{vals[2]/vals[1]*100:.1f}%")
    c[2].metric("Comments / likes", f"{vals[3]/vals[2]*100:.1f}%")
    c[3].metric("Saves / reach", f"{vals[5]/vals[1]*100:.2f}%")

# ------------------------------- Hashtags ------------------------------------
with tabs[5]:
    ex = df.assign(Hashtag=df["Hashtags"].str.split(", ")).explode("Hashtag")
    ht = ex.groupby("Hashtag").agg(Posts=("Post_ID", "count"), ER=("ER", "mean"),
                                   Reach=("Reach", "mean")).reset_index().sort_values("ER", ascending=False)
    c1, c2 = st.columns(2)
    fig = px.bar(ht, x="ER", y="Hashtag", orientation="h", text=ht.ER.map("{:.2f}%".format),
                 title="Avg engagement rate by hashtag")
    fig.update_traces(marker_color=PINK)
    fig.update_layout(yaxis=dict(autorange="reversed"))
    c1.plotly_chart(style(fig), width="stretch")
    fig = px.pie(ht, names="Hashtag", values="Posts", hole=.5, title="Hashtag usage share")
    c2.plotly_chart(style(fig), width="stretch")
    combo = (df.groupby("Hashtags").agg(Posts=("Post_ID", "count"), ER=("ER", "mean"), Reach=("Reach", "mean"))
             .query("Posts >= 30").sort_values("ER", ascending=False).head(10).reset_index())
    fig = px.bar(combo, x="ER", y="Hashtags", orientation="h", color="Reach", color_continuous_scale="RdPu",
                 title="Top 10 hashtag combinations by engagement rate (min. 30 posts)")
    fig.update_layout(yaxis=dict(autorange="reversed"))
    st.plotly_chart(style(fig, 420), width="stretch")

# ------------------------------- Audience ------------------------------------
with tabs[6]:
    c1, c2 = st.columns(2)
    e = df.groupby("Audience_Emotion").agg(ER=("ER", "mean"), Posts=("Post_ID", "count")).reset_index()
    fig = px.bar(e.sort_values("ER"), x="ER", y="Audience_Emotion", orientation="h",
                 text=e.sort_values("ER").ER.map("{:.2f}%".format), title="Engagement rate by audience emotion")
    fig.update_traces(marker_color=PINK)
    c1.plotly_chart(style(fig), width="stretch")
    s = df.groupby("Engagement_Source").agg(Reach=("Reach", "mean"), ER=("ER", "mean"),
                                            Follows=("Follows", "mean")).reset_index()
    fig = px.scatter(s, x="Reach", y="ER", size="Follows", color="Engagement_Source", text="Engagement_Source",
                     title="Source quality: reach vs engagement (bubble = avg follows)")
    fig.update_traces(textposition="top center")
    c2.plotly_chart(style(fig), width="stretch")
    g = df.groupby("Month").agg(Follows=("Follows", "sum")).reset_index()
    g["Cumulative"] = g.Follows.cumsum()
    fig = go.Figure()
    fig.add_bar(x=g.Month, y=g.Follows, name="New follows", marker_color="#F8BBD0")
    fig.add_scatter(x=g.Month, y=g.Cumulative, name="Cumulative", yaxis="y2", line=dict(color=PINK, width=3))
    fig.update_layout(title="Follower growth (new follows attributed to posts)",
                      yaxis2=dict(overlaying="y", side="right", showgrid=False))
    st.plotly_chart(style(fig), width="stretch")
    fig = px.bar(df.groupby("Campaign_Type")["Follow_Conv"].mean().reset_index(), x="Campaign_Type",
                 y="Follow_Conv", title="Profile-visit → follow conversion (%) by campaign",
                 text_auto=".1f")
    fig.update_traces(marker_color=DARK)
    st.plotly_chart(style(fig), width="stretch")

# ------------------------------- Top posts -----------------------------------
with tabs[7]:
    show = ["Label", "Likes", "Comments", "Shares", "Saves", "Reach", "ER", "Hashtags"]
    c1, c2 = st.columns(2)
    t1 = df.nlargest(10, "Likes")
    fig = px.bar(t1, x="Likes", y="Label", orientation="h", title="Top 10 posts by likes")
    fig.update_traces(marker_color=PINK)
    fig.update_layout(yaxis=dict(autorange="reversed", title=""))
    c1.plotly_chart(style(fig, 440), width="stretch")
    t2 = df.nlargest(10, "ER")
    fig = px.bar(t2, x="ER", y="Label", orientation="h", title="Top 10 posts by engagement rate (%)")
    fig.update_traces(marker_color=DARK)
    fig.update_layout(yaxis=dict(autorange="reversed", title=""))
    c2.plotly_chart(style(fig, 440), width="stretch")
    st.subheader("Details")
    st.dataframe(t2[show].round(2), width="stretch", hide_index=True)
    st.caption("The dataset has no caption column, so posts are identified by ID · date · type · campaign.")

# ------------------------------- Insights & AI -------------------------------
with tabs[8]:
    st.subheader("Auto-generated insights (update with filters)")
    findings = {}
    for col, name in [("Post_Type", "post type"), ("Weekday", "weekday"), ("Campaign_Type", "campaign"),
                      ("Engagement_Source", "engagement source"), ("Audience_Emotion", "audience emotion")]:
        b, bv, w, wv, sp = spread(df, col)
        findings[name] = (b, bv, w, wv, sp)
        st.markdown(f'<div class="insight"><b>Best {name}:</b> {b} ({bv:.2f}% ER) vs weakest {w} '
                    f'({wv:.2f}%) — a {sp:.1f}% relative gap.</div>', unsafe_allow_html=True)
    tag_best = ht.iloc[0]
    st.markdown(f'<div class="insight"><b>Best hashtag:</b> {tag_best.Hashtag} ({tag_best.ER:.2f}% ER).</div>',
                unsafe_allow_html=True)
    max_gap = max(v[4] for v in findings.values())
    if max_gap < 5:
        st.info(f"Honest read: the largest gap between any two segments is only {max_gap:.1f}%. Performance is "
                "very uniform, so treat these as hypotheses to A/B test, not proven winners.")

    st.subheader("Recommended strategy")
    st.markdown(f"""
- **Content:** lean into **{findings['post type'][0]}** and **{findings['campaign'][0]}** campaigns, but keep a mix — format gaps are narrow.
- **Timing:** prioritise **{findings['weekday'][0]}**; test slots on **{findings['weekday'][2]}** with stronger creative.
- **Reach:** scale **{findings['engagement source'][0]}**-sourced content; audit the weakest source (**{findings['engagement source'][2]}**) for ROI.
- **Hashtags:** build the core set around **{tag_best.Hashtag}**; run controlled tests on combinations.
- **Growth:** improve profile-visit → follow conversion with bio/CTA tweaks and highlight reels of top campaigns.
- **Consistency:** keep monthly volume steady; dips in posting precede dips in reach.
""")

    st.subheader("🤖 Ask the data (optional AI assistant)")
    key = secret("ANTHROPIC_API_KEY")
    q = st.text_input("Ask a question about the filtered data",
                      placeholder="Which campaign should we double down on, and why?")
    if q:
        if not key:
            st.info("Add ANTHROPIC_API_KEY to Streamlit secrets to enable this. Insights above work without it.")
        else:
            ctx = "\n\n".join([
                f"KPIs: posts={len(df)}, likes={df.Likes.sum()}, comments={df.Comments.sum()}, reach={df.Reach.sum()}, avgER={df.ER.mean():.2f}%",
                *[f"ER by {c}:\n{df.groupby(c, observed=True).ER.mean().round(3).to_string()}"
                  for c in ["Post_Type", "Campaign_Type", "Weekday", "Engagement_Source", "Audience_Emotion"]],
                f"ER by hashtag:\n{ht.set_index('Hashtag').ER.round(3).to_string()}"])
            try:
                import anthropic
                msg = anthropic.Anthropic(api_key=key).messages.create(
                    model=secret("ANTHROPIC_MODEL", "claude-sonnet-5-5"), max_tokens=600,
                    system="You are a social-media analyst. Answer only from the aggregates given; "
                           "state when differences are too small to be meaningful.",
                    messages=[{"role": "user", "content": f"{ctx}\n\nQuestion: {q}"}])
                st.write(msg.content[0].text)
            except Exception as ex:  # noqa: BLE001
                st.error(f"AI request failed: {ex}")

st.markdown("---")
st.caption("Built with Streamlit & Plotly · Riya Gupta")
