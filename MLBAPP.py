import streamlit as st
import pandas as pd
import datetime
import plotly.graph_objects as go
from pybaseball import playerid_lookup, statcast_batter, batting_stats
import statsapi

st.set_page_config(layout="wide")

@st.cache_data
def get_player_id(first, last):
    try:
        return playerid_lookup(last, first).iloc[0]['key_mlbam']
    except:
        return None

@st.cache_data
def get_statcast_data(player_id):
    end = datetime.date.today()
    start = end - datetime.timedelta(days=60)
    df = statcast_batter(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), player_id)

    if df.empty or "events" not in df.columns:
        return pd.DataFrame(columns=["game_date", "1B", "2B", "3B", "HR", "TB", "H", "RBI", "opponent"])

    df = df[df["events"].notnull()]

    # Team and Opponent Columns
    df["player_team"] = df.apply(
        lambda row: row["away_team"] if row["inning_topbot"] == "Top" else row["home_team"], axis=1)
    df["opponent"] = df.apply(
        lambda row: row["home_team"] if row["inning_topbot"] == "Top" else row["away_team"], axis=1)

    # Event-Based Stats
    df["1B"] = (df["events"] == "single").astype(int)
    df["2B"] = (df["events"] == "double").astype(int)
    df["3B"] = (df["events"] == "triple").astype(int)
    df["HR"] = (df["events"] == "home_run").astype(int)
    df["TB"] = df["1B"] + df["2B"] * 2 + df["3B"] * 3 + df["HR"] * 4
    df["H"] = df["1B"] + df["2B"] + df["3B"] + df["HR"]

    # Proper RBI Handling
    if "rbi" in df.columns:
        df["RBI"] = pd.to_numeric(df["rbi"], errors="coerce").fillna(0).astype(int)
    else:
        df["RBI"] = 0

    return df


@st.cache_data
def get_season_stats(name):
    year = datetime.date.today().year
    df = batting_stats(year, qual=0)
    return df[df['Name'].str.contains(name, case=False)]

@st.cache_data
def get_career_stats(name):
    years = list(range(2015, datetime.date.today().year + 1))
    full_data = []
    for y in years:
        df = batting_stats(y, qual=0)
        player_df = df[df['Name'].str.contains(name, case=False)]
        if not player_df.empty:
            player_df["Season"] = y
            full_data.append(player_df)
    return pd.concat(full_data, ignore_index=True) if full_data else pd.DataFrame()

def calculate_hit_rates(df, category, trend_values):
    results = []
    for t in trend_values:
        hits = df[category] >= t
        results.append({
            "Trend": f"{category} ≥ {t}",
            "Last 10": f"{hits.iloc[-10:].sum()}/10 ({(hits.iloc[-10:].sum()/10)*100:.0f}%)",
            "Last 5": f"{hits.iloc[-5:].sum()}/5 ({(hits.iloc[-5:].sum()/5)*100:.0f}%)",
            "Last 3": f"{hits.iloc[-3:].sum()}/3 ({(hits.iloc[-3:].sum()/3)*100:.0f}%)"
        })
    return pd.DataFrame(results)

def predict_next_game_stat(season_avg, vs_team_avg, recent_avg):
    weights = [0.4, 0.3, 0.3]
    return round(
        (season_avg * weights[0]) +
        (vs_team_avg * weights[1]) +
        (recent_avg * weights[2]), 2
    )

# --- App Start ---
st.title("⚾ MLB Player Trend Analyzer")

player_name = st.text_input("Enter player name (e.g. Shohei Ohtani):")
if player_name:
    try:
        first, last = player_name.split(" ")
        player_id = get_player_id(first, last)
        statcast_df = get_statcast_data(player_id)

        opponent_input = st.text_input("Filter by Opponent (Optional):")
        df_filtered = statcast_df[statcast_df["opponent"].str.contains(opponent_input, case=False, na=False)] if opponent_input else statcast_df

        # --- Player Bio ---
        bio = statsapi.get("person", {"personId": player_id})["people"][0]
        st.subheader("🧬 Player Bio")
        age = datetime.datetime.now().year - int(bio["birthDate"][:4])
        bio_data = {
            "Full Name": bio["fullName"],
            "Birthday": pd.to_datetime(bio["birthDate"]).strftime("%B %d, %Y"),
            "Age": age,
            "Height": bio.get("height", "N/A"),
            "Weight": bio.get("weight", "N/A"),
            "Position": bio.get("primaryPosition", {}).get("abbreviation", "N/A"),
            "Debut": bio.get("mlbDebutDate", "N/A"),
            "Team": bio.get("currentTeam", {}).get("name", "N/A"),
            "Bat/Throw": f"{bio.get('batSide', {}).get('description', '')}/{bio.get('pitchHand', {}).get('description', '')}"
        }
        st.table(pd.DataFrame(bio_data.items(), columns=["Attribute", "Value"]))

      
        # --- Season Stats ---
        if st.button("📅 Show Season Averages"):
            st.subheader("📅 Current Season Stats")
            season_df = get_season_stats(player_name)
            if not season_df.empty:
                row = season_df.iloc[0]
                g = row["G"] or 1
                st.dataframe(season_df[["Team", "G", "AB", "H", "HR", "RBI", "SB", "BB", "SO", "OPS"]])
                st.markdown("**Per Game Averages**")
                st.json({
                    "HR/Game": round(row["HR"] / g, 2),
                    "RBI/Game": round(row["RBI"] / g, 2),
                    "BB/Game": round(row["BB"] / g, 2),
                    "K/Game": round(row["SO"] / g, 2),
                    "OPS": round(row["OPS"], 3)
                })

        # --- Career Stats ---
        if st.button("📜 Load Full Career Stats (Slow)"):
            career_df = get_career_stats(player_name)
            if not career_df.empty:
                st.subheader("📊 Full Career Stats")
                st.dataframe(career_df[["Season", "Team", "G", "AB", "H", "HR", "RBI", "BB", "SO", "OPS"]])
            else:
                st.warning("No career data available.")
                
        with st.expander("📊 Trend Analysis + Hit Rate Summary + Predictions"):
            category_display_map = {
                'Singles': '1B',
                'Doubles': '2B',
                'Triples': '3B',
                'Home Runs': 'HR',
                'Total Bases': 'TB',
                'Hits': 'H',
            }
        
            display_to_short = {v: k for k, v in category_display_map.items()}
        
            category_display = st.selectbox("Select a Category:", list(category_display_map.keys()))
            category = category_display_map[category_display]
            trend_input = st.text_input("Enter Trend Values (comma-separated):", value="1,2")
            trend_values = [int(x.strip()) for x in trend_input.split(",") if x.strip().isdigit()]
            display_name = category_display
        
            game_stats = df_filtered.groupby(["game_date", "opponent"])[["1B", "2B", "3B", "HR", "TB", "H", "RBI"]].sum().reset_index()
            game_stats = game_stats.sort_values("game_date", ascending=False).head(10).sort_values("game_date")
            game_stats["bar_color"] = game_stats["TB"].apply(lambda x: "#0c2c57" if x == 0 else "#1f77b4")
        
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=game_stats["game_date"],
                y=game_stats[category],
                marker_color=game_stats["bar_color"],
                hovertext=game_stats.apply(
                    lambda row: f"<b>Date</b>: {row['game_date']}<br><b>Opponent</b>: {row['opponent']}<br><b>{display_name}</b>: {row[category]}", axis=1
                ),
                hoverinfo="text"
            ))
        
            for t in trend_values:
                fig.add_trace(go.Scatter(
                    x=game_stats["game_date"],
                    y=[t]*len(game_stats),
                    mode="lines",
                    name=f"<b>{display_name} ≥ {t}</b>",
                    line=dict(dash='dash', color='orange', width=2)
                ))
        
            fig.update_layout(xaxis_title="Game Date", yaxis_title=display_name, height=500, showlegend=True)
            st.plotly_chart(fig)
        
            st.write("### 📊 Hit Rate Summary")
            st.dataframe(calculate_hit_rates(game_stats, category, trend_values))
        
            if opponent_input:
                st.write(f"### 🔮 Predicted Stat Line vs. {opponent_input.title()}")
                categories = ["1B", "2B", "3B", "HR", "TB"]
                stat_line = {}
                for cat in categories:
                    season_avg = statcast_df.groupby("game_date")[[cat]].sum()[cat].mean()
                    vs_team_avg = df_filtered.groupby("game_date")[[cat]].sum()[cat].mean() if not df_filtered.empty else 0
                    recent_avg = game_stats[cat].mean()
                    stat_line[cat] = predict_next_game_stat(season_avg, vs_team_avg, recent_avg)
        
                st.markdown("#### 🧮 **Expected Performance:**")
                st.markdown(f"""
                - **Singles (1B)**: <span style='color:#1f77b4; font-weight:bold'>{round(stat_line['1B'] * 100)}%</span> chance  
                - **Doubles (2B)**: <span style='color:#1f77b4; font-weight:bold'>{round(stat_line['2B'] * 100)}%</span> chance  
                - **Triples (3B)**: <span style='color:#1f77b4; font-weight:bold'>{round(stat_line['3B'] * 100)}%</span> chance  
                - **Home Runs (HR)**: <span style='color:#c0392b; font-weight:bold'>{round(stat_line['HR'] * 100)}%</span> chance  
                - **Total Bases (TB)**: <span style='color:#2c3e50; font-weight:bold'>{stat_line['TB']}</span> bases expected
                """, unsafe_allow_html=True)


        # --- Statcast Display ---
        st.subheader("📈 Last 10 At-Bats (Statcast)")
        last_10 = statcast_df[statcast_df["events"].notnull()].sort_values("game_date", ascending=False).head(10)
        st.dataframe(last_10[[
            "game_date", "events", "description", "pitch_name", "launch_speed", "launch_angle", "hit_distance_sc"
        ]].rename(columns={
            "game_date": "Date", "events": "Event", "description": "Result",
            "pitch_name": "Pitch", "launch_speed": "Launch Speed", "launch_angle": "Angle", "hit_distance_sc": "Distance"
        }))


    except Exception as e:
        st.error(f"Error: {e}")
