import math
import os
from datetime import date, timedelta

import requests
import streamlit as st

API_BASE = "https://v3.football.api-sports.io"

st.set_page_config(page_title="FOOTBALL AI PRO", page_icon="⚽", layout="wide")

def poisson(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def build_matrix(lh, la, max_goals=10):
    ph = [poisson(i, lh) for i in range(max_goals + 1)]
    pa = [poisson(i, la) for i in range(max_goals + 1)]
    return [[x * y for y in pa] for x in ph]

def analyze(home, away, home_attack, home_defence, away_attack, away_defence,
            league_home_avg=1.50, league_away_avg=1.15, max_goals=10):
    # Team rates are venue-specific goals scored/conceded per match.
    # Strength ratios are normalized against the league's home/away averages.
    ha = max(0.05, home_attack / max(0.1, league_home_avg))
    hd = max(0.05, home_defence / max(0.1, league_away_avg))
    aa = max(0.05, away_attack / max(0.1, league_away_avg))
    ad = max(0.05, away_defence / max(0.1, league_home_avg))
    lh = max(0.05, league_home_avg * ha * ad)
    la = max(0.05, league_away_avg * aa * hd)
    m = build_matrix(lh, la, max_goals)
    p1 = sum(m[h][a] for h in range(max_goals+1) for a in range(max_goals+1) if h > a)
    px = sum(m[h][a] for h in range(max_goals+1) for a in range(max_goals+1) if h == a)
    p2 = sum(m[h][a] for h in range(max_goals+1) for a in range(max_goals+1) if h < a)
    total = lambda threshold: sum(m[h][a] for h in range(max_goals+1) for a in range(max_goals+1) if h+a > threshold)
    btts = sum(m[h][a] for h in range(1,max_goals+1) for a in range(1,max_goals+1))
    scores = sorted(((m[h][a], h, a) for h in range(max_goals+1) for a in range(max_goals+1)), reverse=True)[:7]
    return {
        "home_lambda": lh, "away_lambda": la, "1": p1, "X": px, "2": p2,
        "1X": p1+px, "X2": px+p2, "12": p1+p2,
        "over15": total(1), "under15": 1-total(1),
        "over25": total(2), "under25": 1-total(2),
        "over35": total(3), "under35": 1-total(3),
        "btts_yes": btts, "btts_no": 1-btts, "scores": scores
    }

def api_get(endpoint, api_key, params=None):
    response = requests.get(
        f"{API_BASE}/{endpoint}",
        headers={"x-apisports-key": api_key},
        params=params or {},
        timeout=25,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(str(payload["errors"]))
    return payload.get("response", [])

def pct(v):
    return f"{100*v:.1f}%"

st.title("⚽ FOOTBALL AI PRO")
st.caption("Motor statistic de probabilități • versiunea 1.0 • estimări, nu garanții")

with st.sidebar:
    st.header("Conectare date")
    api_key = st.text_input("API-FOOTBALL key", type="password",
        help="Cheia se obține de la API-Sports / API-Football. Poți folosi aplicația și fără cheie, cu introducere manuală.")
    st.caption("Cheia este folosită doar în sesiunea curentă și nu este salvată de aplicație.")
    st.divider()
    st.markdown("**Model**")
    st.write("Poisson independent, rate normalizate la mediile ligii.")
    st.caption("Pentru uz serios: validează datele și testează modelul pe sezoane anterioare.")

tab_auto, tab_manual, tab_help = st.tabs(["📅 Meciuri din API", "🧮 Analiză manuală", "ℹ️ Ghid"])

with tab_auto:
    st.subheader("Meciuri programate")
    c1, c2 = st.columns([1, 2])
    with c1:
        match_date = st.date_input("Data meciurilor", value=date.today())
        fetch = st.button("Încarcă meciurile", type="primary", disabled=not bool(api_key))
    with c2:
        st.info("API-ul poate avea limite de cereri și acoperire diferită pe competiții. Nu toate planurile oferă aceleași date.")
    if not api_key:
        st.warning("Introdu cheia API în bara din stânga pentru a încărca automat programul.")
    if fetch:
        try:
            fixtures = api_get("fixtures", api_key, {"date": match_date.isoformat(), "timezone": "Europe/Bucharest"})
            st.session_state["fixtures"] = fixtures
            st.session_state["fixture_date"] = match_date.isoformat()
        except Exception as exc:
            st.error(f"Nu am putut încărca meciurile: {exc}")
    fixtures = st.session_state.get("fixtures", [])
    if fixtures:
        labels = []
        for f in fixtures:
            teams = f.get("teams", {})
            league = f.get("league", {})
            fixture = f.get("fixture", {})
            labels.append(f'{fixture.get("date","")[:16].replace("T"," ")} | {league.get("name","")} | {teams.get("home",{}).get("name","")} - {teams.get("away",{}).get("name","")}')
        selected = st.selectbox("Alege un meci", range(len(labels)), format_func=lambda i: labels[i])
        f = fixtures[selected]
        teams, league = f.get("teams", {}), f.get("league", {})
        home = teams.get("home", {}).get("name", "Gazde")
        away = teams.get("away", {}).get("name", "Oaspeți")
        league_id = league.get("id")
        season = league.get("season")
        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")
        st.write(f"**{home} – {away}** · {league.get('name','')} · sezon {season}")
        if st.button("Analizează cu statisticile echipelor"):
            try:
                hs = api_get("teams/statistics", api_key, {"league": league_id, "season": season, "team": home_id})
                aws = api_get("teams/statistics", api_key, {"league": league_id, "season": season, "team": away_id})
                if not isinstance(hs, dict) or not isinstance(aws, dict) or not hs or not aws:
                    raise RuntimeError("API-ul nu a returnat statisticile pentru ambele echipe.")
                # API-Sports average fields are strings and may be unavailable ("-" or null).
                def avg(obj, side, group):
                    value = obj.get("goals", {}).get(group, {}).get("average", {}).get(side)
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        return None
                h_for = avg(hs, "home", "for")
                h_against = avg(hs, "home", "against")
                a_for = avg(aws, "away", "for")
                a_against = avg(aws, "away", "against")
                if None in (h_for, h_against, a_for, a_against):
                    raise RuntimeError("Lipsesc medii de goluri acasă/deplasare. Folosește analiza manuală.")
                # League averages are configurable proxies until league-wide stats are added.
                result = analyze(home, away, h_for, h_against, a_for, a_against)
                st.session_state["last_result"] = (home, away, result, "API: statistici sezon/teren")
            except Exception as exc:
                st.error(f"Analiza automată nu este disponibilă pentru acest meci: {exc}")
                st.info("Poți introduce mediile verificate în fila «Analiză manuală».")
    if "last_result" in st.session_state:
        home, away, r, source = st.session_state["last_result"]
        st.divider()
        st.subheader(f"Rezultat: {home} – {away}")
        st.caption(source + " · model Poisson")
        cols = st.columns(3)
        for col, key, label in zip(cols, ["1","X","2"], ["Victorie gazde","Egal","Victorie oaspeți"]):
            col.metric(label, pct(r[key]))
        st.write("**Piețe de goluri și ambele marchează**")
        cols = st.columns(4)
        for col, key, label in zip(cols, ["over15","over25","under25","btts_yes"],
                                   ["Peste 1,5","Peste 2,5","Sub 2,5","GG – Da"]):
            col.metric(label, pct(r[key]))
        st.write("**Scoruri exacte cu probabilitatea cea mai mare**")
        st.dataframe([{"Scor": f"{home} {h}-{a} {away}", "Probabilitate": pct(p)} for p,h,a in r["scores"]], use_container_width=True)

with tab_manual:
    st.subheader("Introdu statisticile echipelor")
    st.caption("Folosește medii pe meci din sezon, separat acasă și în deplasare. Ideal: eșantion suficient și aceeași competiție.")
    c1, c2 = st.columns(2)
    with c1:
        home = st.text_input("Echipa gazdă", "Echipa gazdă")
        h_for = st.number_input("Goluri marcate de gazde acasă / meci", 0.0, 6.0, 1.55, 0.05)
        h_against = st.number_input("Goluri primite de gazde acasă / meci", 0.0, 6.0, 0.95, 0.05)
    with c2:
        away = st.text_input("Echipa oaspete", "Echipa oaspete")
        a_for = st.number_input("Goluri marcate de oaspeți în deplasare / meci", 0.0, 6.0, 1.10, 0.05)
        a_against = st.number_input("Goluri primite de oaspeți în deplasare / meci", 0.0, 6.0, 1.45, 0.05)
    c3, c4 = st.columns(2)
    with c3:
        l_home = st.number_input("Media ligii: goluri gazde", 0.5, 3.5, 1.50, 0.05)
    with c4:
        l_away = st.number_input("Media ligii: goluri oaspeți", 0.5, 3.5, 1.15, 0.05)
    if st.button("Calculează probabilitățile", type="primary"):
        r = analyze(home, away, h_for, h_against, a_for, a_against, l_home, l_away)
        st.subheader(f"{home} – {away}")
        cols = st.columns(3)
        for col, key, label in zip(cols, ["1","X","2"], ["1 – Gazde","X – Egal","2 – Oaspeți"]):
            col.metric(label, pct(r[key]))
        cols = st.columns(5)
        for col, key, label in zip(cols, ["over15","over25","under25","over35","btts_yes"],
                                   ["Peste 1,5","Peste 2,5","Sub 2,5","Peste 3,5","GG – Da"]):
            col.metric(label, pct(r[key]))
        st.write("**Scoruri exacte cele mai probabile**")
        st.dataframe([{"Scor": f"{home} {h}-{a} {away}", "Probabilitate": pct(p)} for p,h,a in r["scores"]], use_container_width=True)
        st.caption(f"Goluri estimate: {home} {r['home_lambda']:.2f} – {r['away_lambda']:.2f} {away}")

with tab_help:
    st.subheader("Cum se folosește")
    st.markdown("""
1. Pentru program automat, obține o cheie API-FOOTBALL de la **api-football.com** și introdu-o în bara din stânga.
2. În fila **Meciuri din API**, alege data, încarcă meciurile și selectează partida.
3. Apasă **Analizează cu statisticile echipelor**. Dacă lipsesc mediile necesare, folosește fila manuală.
4. În fila **Analiză manuală**, introdu mediile golurilor marcate/primite, separat acasă și în deplasare.

**Limitări importante**
- Versiunea aceasta nu verifică automat accidentările, suspendările, forma ultimelor 5–10 meciuri, xG sau cotele.
- API-ul poate returna date incomplete în funcție de ligă și abonament.
- Modelul Poisson prezentat este un punct de pornire, nu un model validat/calibrat pentru pariuri.
- Probabilitățile nu sunt garanții și nu trebuie interpretate drept recomandări certe.
""")
    st.link_button("Deschide API-Football", "https://www.api-football.com/")
    st.warning("Joacă responsabil. Nu există metodă care să garanteze câștigul.")
