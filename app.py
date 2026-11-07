import math
from datetime import date, timedelta
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="FOOTBALL AI PRO", page_icon="⚽", layout="wide")

BASE_URL = "https://v3.football.api-sports.io"

def api_get(endpoint, api_key, params=None):
    headers = {"x-apisports-key": api_key}
    try:
        response = requests.get(
            f"{BASE_URL}/{endpoint}",
            headers=headers,
            params=params or {},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Nu s-a putut contacta API-FOOTBALL: {exc}") from exc

    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError(f"API-FOOTBALL a trimis un răspuns invalid (HTTP {response.status_code}).")

    if response.status_code != 200:
        raise RuntimeError(f"API-FOOTBALL HTTP {response.status_code}: {payload}")

    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"API-FOOTBALL a raportat: {errors}")

    return payload.get("response", []), payload.get("results", 0)

def poisson(lam, goals):
    return math.exp(-lam) * (lam ** goals) / math.factorial(goals)

def match_probabilities(home_lambda, away_lambda, max_goals=8):
    p_home = p_draw = p_away = 0.0
    totals = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}
    gg = 0.0
    scores = []
    for h in range(max_goals + 1):
        ph = poisson(home_lambda, h)
        for a in range(max_goals + 1):
            p = ph * poisson(away_lambda, a)
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p
            if h + a > 1:
                totals[1.5] += p
            if h + a > 2:
                totals[2.5] += p
            if h + a > 3:
                totals[3.5] += p
            if h > 0 and a > 0:
                gg += p
            scores.append((p, h, a))
    total = p_home + p_draw + p_away
    if total:
        p_home, p_draw, p_away = p_home/total, p_draw/total, p_away/total
    return {
        "1": p_home, "X": p_draw, "2": p_away,
        "GG": gg, "NG": 1-gg,
        "Over 1.5": totals[1.5], "Over 2.5": totals[2.5], "Over 3.5": totals[3.5],
        "Under 1.5": 1-totals[1.5], "Under 2.5": 1-totals[2.5], "Under 3.5": 1-totals[3.5],
        "scores": sorted(scores, reverse=True)[:5],
    }

def completed_fixtures(rows):
    done = []
    for item in rows:
        fixture = item.get("fixture", {})
        status = fixture.get("status", {}).get("short", "")
        goals = item.get("goals", {})
        if status in ("FT", "AET", "PEN") and goals.get("home") is not None and goals.get("away") is not None:
            done.append(item)
    return sorted(done, key=lambda x: x.get("fixture", {}).get("timestamp", 0), reverse=True)

def team_recent(team_id, api_key, today):
    # Compatibil cu planul gratuit: folosim intervalul from/to.
    # NU folosim parametrul last, care nu este disponibil pe Free.
    start = today - timedelta(days=365)
    rows, _ = api_get(
        "fixtures",
        api_key,
        {
            "team": team_id,
            "from": start.isoformat(),
            "to": today.isoformat(),
            "timezone": "Europe/Bucharest",
        },
    )
    return completed_fixtures(rows)[:10]

def team_rates(fixtures, team_id, home_venue):
    scored, conceded = [], []
    for item in fixtures:
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        is_home = teams.get("home", {}).get("id") == team_id
        own = goals.get("home") if is_home else goals.get("away")
        opp = goals.get("away") if is_home else goals.get("home")
        if own is not None and opp is not None:
            scored.append(float(own))
            conceded.append(float(opp))
    if not scored:
        return None
    return sum(scored)/len(scored), sum(conceded)/len(conceded)

def expected_goals(home_rows, away_rows, home_id, away_id):
    h_all = team_rates(home_rows, home_id, True)
    a_all = team_rates(away_rows, away_id, False)
    if not h_all or not a_all:
        raise RuntimeError("Nu există suficiente meciuri terminate în ultimele 365 de zile pentru ambele echipe.")
    # Estimare simplificată din golurile marcate și primite recent.
    h_attack = (h_all[0] + a_all[1]) / 2
    a_attack = (a_all[0] + h_all[1]) / 2
    return max(0.15, min(4.0, h_attack)), max(0.15, min(4.0, a_attack))

st.title("⚽ FOOTBALL AI PRO")
st.caption("Analiză statistică orientativă pe baza meciurilor recente. Nu garantează rezultate și nu reprezintă recomandare de pariere.")

with st.sidebar:
    st.header("Conectare API")
    api_key = st.text_input("API-Football Key", type="password", help="Cheia rămâne doar în sesiunea curentă.")
    st.caption("Nu trimite cheia nimănui și nu o publica pe GitHub.")
    st.divider()
    st.write("Plan Free: aplicația folosește intervale de date, nu parametrul `last`.")

if not api_key:
    st.info("Introdu cheia API-Football în meniul din stânga pentru a încărca meciurile.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["Meciuri și analiză", "Analiză manuală", "Verificare API"])

with tab1:
    selected_date = st.date_input("Data meciurilor", value=date.today())
    if st.button("Încarcă meciurile", type="primary"):
        try:
            rows, _ = api_get("fixtures", api_key, {
                "date": selected_date.isoformat(),
                "timezone": "Europe/Bucharest",
            })
            st.session_state["fixtures_for_date"] = rows
            st.session_state["fixtures_date"] = selected_date.isoformat()
        except Exception as exc:
            st.error(str(exc))

    rows = st.session_state.get("fixtures_for_date", [])
    if st.session_state.get("fixtures_date") == selected_date.isoformat() and rows:
        options = []
        lookup = {}
        for item in rows:
            fixture = item.get("fixture", {})
            teams = item.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            label = f'{home.get("name", "Gazde")} - {away.get("name", "Oaspeți")} | {fixture.get("date", "")[:16]}'
            options.append(label)
            lookup[label] = item
        chosen = st.selectbox("Alege meciul", options)
        match = lookup[chosen]
        home = match["teams"]["home"]
        away = match["teams"]["away"]
        st.subheader(f'{home.get("name")} - {away.get("name")}')
        if st.button("Analizează meciul selectat", type="primary"):
            try:
                with st.spinner("Analizez ultimele meciuri disponibile..."):
                    home_recent = team_recent(home["id"], api_key, selected_date)
                    away_recent = team_recent(away["id"], api_key, selected_date)
                    hl, al = expected_goals(home_recent, away_recent, home["id"], away["id"])
                    probs = match_probabilities(hl, al)
                c1, c2, c3 = st.columns(3)
                c1.metric("Victorie gazde (1)", f"{probs['1']*100:.1f}%")
                c2.metric("Egal (X)", f"{probs['X']*100:.1f}%")
                c3.metric("Victorie oaspeți (2)", f"{probs['2']*100:.1f}%")
                st.write(f"Goluri estimate: **{hl:.2f} – {al:.2f}**")
                st.subheader("Piețe statistice")
                market_rows = [
                    {"Piață": key, "Probabilitate": f"{probs[key]*100:.1f}%"}
                    for key in ["GG", "NG", "Over 1.5", "Under 1.5", "Over 2.5", "Under 2.5", "Over 3.5", "Under 3.5"]
                ]
                st.dataframe(pd.DataFrame(market_rows), use_container_width=True, hide_index=True)
                st.subheader("Scoruri exacte cu probabilitate estimată")
                st.dataframe(pd.DataFrame([
                    {"Scor": f"{h}-{a}", "Probabilitate": f"{p*100:.1f}%"}
                    for p, h, a in probs["scores"]
                ]), use_container_width=True, hide_index=True)
                st.caption(f"Eșantion folosit: {len(home_recent)} meciuri pentru gazde și {len(away_recent)} pentru oaspeți.")
            except Exception as exc:
                st.error(f"Analiza nu a putut fi calculată: {exc}")
    elif st.session_state.get("fixtures_date") == selected_date.isoformat():
        st.warning("Nu au fost găsite meciuri pentru data aleasă.")

with tab2:
    st.subheader("Analiză manuală")
    c1, c2 = st.columns(2)
    with c1:
        home_name = st.text_input("Echipa gazdă", "Gazde")
        home_scored = st.number_input("Media golurilor marcate de gazde", min_value=0.0, max_value=5.0, value=1.4, step=0.1)
        home_conceded = st.number_input("Media golurilor primite de gazde", min_value=0.0, max_value=5.0, value=1.1, step=0.1)
    with c2:
        away_name = st.text_input("Echipa oaspete", "Oaspeți")
        away_scored = st.number_input("Media golurilor marcate de oaspeți", min_value=0.0, max_value=5.0, value=1.2, step=0.1)
        away_conceded = st.number_input("Media golurilor primite de oaspeți", min_value=0.0, max_value=5.0, value=1.3, step=0.1)
    if st.button("Calculează analiza manuală"):
        hl = max(0.15, (home_scored + away_conceded)/2)
        al = max(0.15, (away_scored + home_conceded)/2)
        probs = match_probabilities(hl, al)
        st.write(f"**{home_name} – {away_name}** | Goluri estimate: {hl:.2f} – {al:.2f}")
        st.write(f"1: **{probs['1']*100:.1f}%** · X: **{probs['X']*100:.1f}%** · 2: **{probs['2']*100:.1f}%**")
        st.write(f"GG: **{probs['GG']*100:.1f}%** · Over 2.5: **{probs['Over 2.5']*100:.1f}%**")

with tab3:
    st.subheader("Verificare conexiune API")
    if st.button("Testează cheia API"):
        try:
            leagues, count = api_get("leagues", api_key, {"current": "true"})
            st.success(f"Conexiune reușită. API-ul a returnat {count} competiții.")
        except Exception as exc:
            st.error(str(exc))
