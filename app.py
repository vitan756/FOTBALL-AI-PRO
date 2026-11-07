import streamlit as st
import requests
import math
import datetime
from collections import defaultdict

# ==========================================
# FOOTBALL AI PRO - GRATUIT
# Motor de probabilitati Poisson
# Fara LIVE
# ==========================================

st.set_page_config(
    page_title="FOOTBALL AI PRO",
    page_icon="⚽",
    layout="wide"
)

API_URL = "https://v3.football.api-sports.io"

st.markdown("""
<style>
.main {
    background-color: #07111f;
}
h1 {
    color: #00d084;
}
h2, h3 {
    color: #ffffff;
}
</style>
""", unsafe_allow_html=True)

st.title("⚽ FOOTBALL AI PRO")
st.caption("Motor gratuit de analiză și probabilități • Model Poisson • Fără LIVE")

# ==========================================
# API
# ==========================================

def api_get(endpoint, params, api_key):
    headers = {"x-apisports-key": api_key}

    try:
        response = requests.get(
            API_URL + endpoint,
            headers=headers,
            params=params,
            timeout=30
        )

        if response.status_code != 200:
            return None, f"Eroare API: HTTP {response.status_code}"

        data = response.json()

        errors = data.get("errors")
        if errors:
            return None, f"API-FOOTBALL: {errors}"

        return data.get("response", []), None

    except requests.exceptions.Timeout:
        return None, "API-ul nu a răspuns la timp."
    except requests.exceptions.RequestException as e:
        return None, f"Eroare de conexiune: {e}"
    except ValueError:
        return None, "Răspunsul API nu este valid."


@st.cache_data(ttl=3600, show_spinner=False)
def get_leagues(api_key, season):
    return api_get(
        "/leagues",
        {"season": season},
        api_key
    )


@st.cache_data(ttl=900, show_spinner=False)
def get_fixtures(api_key, league_id, season, match_date):
    return api_get(
        "/fixtures",
        {
            "league": league_id,
            "season": season,
            "date": match_date,
            "timezone": "Europe/Bucharest"
        },
        api_key
    )


@st.cache_data(ttl=3600, show_spinner=False)
def get_history(api_key, league_id, season, date_from, date_to):
    return api_get(
        "/fixtures",
        {
            "league": league_id,
            "season": season,
            "from": date_from,
            "to": date_to,
            "timezone": "Europe/Bucharest"
        },
        api_key
    )


# ==========================================
# MODEL POISSON
# ==========================================

def poisson_probability(goals, expected_goals):
    return (
        math.exp(-expected_goals)
        * expected_goals ** goals
        / math.factorial(goals)
    )


def poisson_analysis(home_lambda, away_lambda):
    results = []

    for home_goals in range(11):
        for away_goals in range(11):
            probability = (
                poisson_probability(home_goals, home_lambda)
                * poisson_probability(away_goals, away_lambda)
            )

            results.append({
                "home": home_goals,
                "away": away_goals,
                "prob": probability
            })

    home_win = sum(
        x["prob"] for x in results if x["home"] > x["away"]
    )
    draw = sum(
        x["prob"] for x in results if x["home"] == x["away"]
    )
    away_win = sum(
        x["prob"] for x in results if x["home"] < x["away"]
    )

    over_15 = sum(
        x["prob"] for x in results
        if x["home"] + x["away"] >= 2
    )

    over_25 = sum(
        x["prob"] for x in results
        if x["home"] + x["away"] >= 3
    )

    under_25 = 1 - over_25

    btts = sum(
        x["prob"] for x in results
        if x["home"] >= 1 and x["away"] >= 1
    )

    top_scores = sorted(
        results,
        key=lambda x: x["prob"],
        reverse=True
    )[:5]

    return {
        "home_win": home_win,
        "draw": draw,
        "away_win": away_win,
        "over_15": over_15,
        "over_25": over_25,
        "under_25": under_25,
        "btts": btts,
        "scores": top_scores,
        "home_lambda": home_lambda,
        "away_lambda": away_lambda
    }


# ==========================================
# STATISTICI ECHIPE
# ==========================================

def completed_match(match):
    status = match.get("fixture", {}).get("status", {}).get("short")
    return status in ["FT", "AET", "PEN"]


def get_team_matches(history, team_id, venue=None):
    matches = []

    for match in history:
        if not completed_match(match):
            continue

        home = match.get("teams", {}).get("home", {})
        away = match.get("teams", {}).get("away", {})
        goals = match.get("goals", {})

        if goals.get("home") is None or goals.get("away") is None:
            continue

        if home.get("id") == team_id:
            if venue is None or venue == "home":
                matches.append({
                    "scored": goals["home"],
                    "conceded": goals["away"]
                })

        elif away.get("id") == team_id:
            if venue is None or venue == "away":
                matches.append({
                    "scored": goals["away"],
                    "conceded": goals["home"]
                })

    matches.sort(
        key=lambda x: 0,
        reverse=True
    )

    return matches[-10:]


def average_stat(matches, field, fallback):
    if not matches:
        return fallback

    values = [m[field] for m in matches]
    return sum(values) / len(values)


def calculate_expected_goals(history, home_id, away_id):
    completed = [
        m for m in history
        if completed_match(m)
        and m.get("goals", {}).get("home") is not None
        and m.get("goals", {}).get("away") is not None
    ]

    if len(completed) < 5:
        return None, None, "Nu există suficiente meciuri istorice."

    home_goals = [
        m["goals"]["home"] for m in completed
    ]
    away_goals = [
        m["goals"]["away"] for m in completed
    ]

    league_home_avg = sum(home_goals) / len(home_goals)
    league_away_avg = sum(away_goals) / len(away_goals)

    if league_home_avg <= 0 or league_away_avg <= 0:
        return None, None, "Statisticile campionatului sunt insuficiente."

    home_home = get_team_matches(history, home_id, "home")
    home_all = get_team_matches(history, home_id)

    away_away = get_team_matches(history, away_id, "away")
    away_all = get_team_matches(history, away_id)

    # Ultimele meciuri de acasă pentru gazde
    if len(home_home) < 3:
        home_home = home_all

    # Ultimele meciuri în deplasare pentru oaspeți
    if len(away_away) < 3:
        away_away = away_all

    home_scored = average_stat(
        home_home, "scored", league_home_avg
    )
    home_conceded = average_stat(
        home_home, "conceded", league_away_avg
    )

    away_scored = average_stat(
        away_away, "scored", league_away_avg
    )
    away_conceded = average_stat(
        away_away, "conceded", league_home_avg
    )

    home_attack = home_scored / league_home_avg
    away_defence = away_conceded / league_home_avg

    away_attack = away_scored / league_away_avg
    home_defence = home_conceded / league_away_avg

    home_lambda = league_home_avg * home_attack * away_defence
    away_lambda = league_away_avg * away_attack * home_defence

    # Evităm valori extreme
    home_lambda = max(0.15, min(home_lambda, 4.5))
    away_lambda = max(0.15, min(away_lambda, 4.5))

    return home_lambda, away_lambda, None


# ==========================================
# BARA LATERALA
# ==========================================

st.sidebar.header("⚙️ Setări")

api_key = st.sidebar.text_input(
    "Cheia API-FOOTBALL",
    type="password",
    help="Cheia nu este salvată în cod."
)

season = st.sidebar.selectbox(
    "Sezon disponibil",
    [2024, 2023, 2022],
    index=0
)

st.sidebar.info(
    "Varianta gratuită. Nu folosește LIVE. "
    "API-FOOTBALL poate limita accesul la anumite sezoane."
)

# ==========================================
# ÎNCĂRCARE CAMPIONATE
# ==========================================

if not api_key:
    st.warning("Introdu cheia API-FOOTBALL în bara laterală.")
    st.stop()

if st.button("🌍 Încarcă toate campionatele", use_container_width=True):
    st.cache_data.clear()

with st.spinner("Se încarcă lista campionatelor..."):
    leagues_data, league_error = get_leagues(api_key, season)

if league_error:
    st.error(league_error)
    st.stop()

if not leagues_data:
    st.warning("API-ul nu a returnat campionate pentru acest sezon.")
    st.stop()

# Eliminăm duplicatele
unique_leagues = {}

for item in leagues_data:
    league = item.get("league", {})
    country = item.get("country", {})

    league_id = league.get("id")
    league_name = league.get("name", "Campionat necunoscut")
    country_name = country.get("name", "")

    if league_id:
        unique_leagues[league_id] = {
            "name": league_name,
            "country": country_name
        }

league_options = sorted(
    unique_leagues.items(),
    key=lambda x: (
        x[1]["country"],
        x[1]["name"]
    )
)

st.success(
    f"Au fost găsite {len(league_options)} campionate."
)

# ==========================================
# SELECTARE CAMPIONAT ȘI DATĂ
# ==========================================

st.subheader("📅 Selectează meciurile")

league_labels = [
    f'{value["name"]} — {value["country"]} (ID {key})'
    for key, value in league_options
]

selected_label = st.selectbox(
    "Campionat",
    league_labels
)

selected_index = league_labels.index(selected_label)
selected_league_id = league_options[selected_index][0]

selected_date = st.date_input(
    "Data meciurilor",
    value=datetime.date(2024, 12, 1),
    min_value=datetime.date(2022, 1, 1),
    max_value=datetime.date(2024, 12, 31)
)

# ==========================================
# ÎNCĂRCARE MECIURI
# ==========================================

if st.button("⚽ Încarcă meciurile", use_container_width=True):
    with st.spinner("Se caută meciurile..."):
        fixtures, fixture_error = get_fixtures(
            api_key,
            selected_league_id,
            season,
            selected_date.isoformat()
        )

    if fixture_error:
        st.error(fixture_error)
        st.stop()

    st.session_state["fixtures"] = fixtures or []
    st.session_state["fixture_date"] = selected_date.isoformat()
    st.session_state["fixture_league"] = selected_league_id

fixtures = st.session_state.get("fixtures", [])

if not fixtures:
    st.info(
        "Apasă «Încarcă meciurile». Dacă nu există meciuri "
        "în ziua aleasă, încearcă altă dată din sezon."
    )
    st.stop()

if (
    st.session_state.get("fixture_date") != selected_date.isoformat()
    or st.session_state.get("fixture_league") != selected_league_id
):
    st.info("Apasă din nou «Încarcă meciurile» pentru selecția nouă.")
    st.stop()

# ==========================================
# SELECTARE MECI
# ==========================================

match_options = []
match_by_label = {}

for match in fixtures:
    home = match.get("teams", {}).get("home", {})
    away = match.get("teams", {}).get("away", {})
    fixture = match.get("fixture", {})
    league = match.get("league", {})

    home_name = home.get("name", "Gazde")
    away_name = away.get("name", "Oaspeți")
    fixture_id = fixture.get("id")

    label = f"{home_name} - {away_name} | {fixture.get('date', '')[:16]}"

    if fixture_id:
        match_options.append(label)
        match_by_label[label] = match

if not match_options:
    st.warning("Nu au fost găsite meciuri valide în această zi.")
    st.stop()

st.success(f"Au fost găsite {len(match_options)} meciuri.")

selected_match_label = st.selectbox(
    "Alege meciul pentru analiză",
    match_options
)

selected_match = match_by_label[selected_match_label]

home_team = selected_match["teams"]["home"]
away_team = selected_match["teams"]["away"]

home_name = home_team["name"]
away_name = away_team["name"]

home_id = home_team["id"]
away_id = away_team["id"]

# ==========================================
# ANALIZĂ MECI
# ==========================================

if st.button(
    "🧠 ANALIZEAZĂ MECIUL SELECTAT",
    type="primary",
    use_container_width=True
):

    match_date = datetime.date.fromisoformat(
        selected_date.isoformat()
    )

    date_from = max(
        datetime.date(season, 1, 1),
        match_date - datetime.timedelta(days=365)
    )

    date_to = match_date - datetime.timedelta(days=1)

    if date_to < date_from:
        st.error("Nu există perioadă istorică înaintea acestui meci.")
        st.stop()

    with st.spinner("Se analizează istoricul echipelor..."):
        history, history_error = get_history(
            api_key,
            selected_league_id,
            season,
            date_from.isoformat(),
            date_to.isoformat()
        )

    if history_error:
        st.error(history_error)
        st.stop()

    if not history:
        st.error("Nu există date istorice pentru acest campionat.")
        st.stop()

    home_lambda, away_lambda, model_error = calculate_expected_goals(
        history,
        home_id,
        away_id
    )

    if model_error:
        st.error(model_error)
        st.stop()

    prediction = poisson_analysis(
        home_lambda,
        away_lambda
    )

    st.divider()
    st.header(f"📊 {home_name} - {away_name}")

    st.caption(
        "Estimare statistică Poisson pe baza meciurilor istorice "
        "disponibile înaintea datei selectate."
    )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        f"Victorie {home_name}",
        f'{prediction["home_win"] * 100:.1f}%'
    )

    col2.metric(
        "Egal",
        f'{prediction["draw"] * 100:.1f}%'
    )

    col3.metric(
        f"Victorie {away_name}",
        f'{prediction["away_win"] * 100:.1f}%'
    )

    st.subheader("⚽ Goluri")

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Peste 1.5 goluri",
        f'{prediction["over_15"] * 100:.1f}%'
    )

    c2.metric(
        "Peste 2.5 goluri",
        f'{prediction["over_25"] * 100:.1f}%'
    )

    c3.metric(
        "Sub 2.5 goluri",
        f'{prediction["under_25"] * 100:.1f}%'
    )

    st.subheader("🥅 Ambele echipe marchează")

    st.metric(
        "GG - Da",
        f'{prediction["btts"] * 100:.1f}%'
    )

    st.subheader("🎯 Goluri estimate")

    c1, c2 = st.columns(2)

    c1.metric(
        home_name,
        f'{prediction["home_lambda"]:.2f}'
    )

    c2.metric(
        away_name,
        f'{prediction["away_lambda"]:.2f}'
    )

    st.subheader("🔢 Cele mai probabile scoruri")

    score_data = []

    for score in prediction["scores"]:
        score_data.append({
            "Scor": f'{score["home"]} - {score["away"]}',
            "Probabilitate": f'{score["prob"] * 100:.2f}%'
        })

    st.table(score_data)

    st.divider()

    st.subheader("📌 Rezumatul modelului")

    probabilities = {
        "1": prediction["home_win"],
        "X": prediction["draw"],
        "2": prediction["away_win"],
        "GG": prediction["btts"],
        "Peste 1.5": prediction["over_15"],
        "Peste 2.5": prediction["over_25"],
        "Sub 2.5": prediction["under_25"]
    }

    best = max(probabilities, key=probabilities.get)

    st.success(
        f"Probabilitatea cea mai mare calculată de model: "
        f"{best} — {probabilities[best] * 100:.1f}%"
    )

    st.warning(
        "Acestea sunt estimări matematice, nu certitudini. "
        "Modelul nu folosește cote, accidentări sau informații LIVE."
    )

# ==========================================
# INFORMATII
# ==========================================

st.divider()

with st.expander("ℹ️ Despre FOOTBALL AI PRO"):
    st.write("""
    - Motor matematic Poisson.
    - Analizează ultimele 10 meciuri disponibile ale echipelor.
    - Calculează probabilități 1X2.
    - Calculează GG și peste/sub goluri.
    - Afișează cele mai probabile scoruri.
    - Nu folosește LIVE.
    - Nu garantează rezultate.
    - Datele depind de accesul oferit de API-FOOTBALL.
    """)
