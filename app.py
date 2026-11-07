import math
import requests
import pandas as pd
import streamlit as st

from datetime import date

# ==========================================
# FOOTBALL AI PRO
# ==========================================

st.set_page_config(
    page_title="FOOTBALL AI PRO",
    page_icon="⚽",
    layout="wide"
)

BASE_URL = "https://v3.football.api-sports.io"


# ==========================================
# CONECTARE API
# ==========================================

def api_get(endpoint, api_key, params=None):
    headers = {"x-apisports-key": api_key}

    try:
        r = requests.get(
            f"{BASE_URL}/{endpoint}",
            headers=headers,
            params=params or {},
            timeout=25
        )

        data = r.json()

        if r.status_code != 200:
            raise Exception(data)

        if data.get("errors"):
            raise Exception(data["errors"])

        return data.get("response", [])

    except requests.RequestException as e:
        raise Exception(f"Eroare conexiune API: {e}")


# ==========================================
# MODEL POISSON
# ==========================================

def poisson(lam, goals):
    return (
        math.exp(-lam)
        * (lam ** goals)
        / math.factorial(goals)
    )


def predictie(lam_h, lam_a, scor_h=0, scor_a=0):
    p1 = 0
    px = 0
    p2 = 0
    gg = 0
    over25 = 0
    rezultate = []

    for h in range(9):
        for a in range(9):
            p = poisson(lam_h, h) * poisson(lam_a, a)

            final_h = h + scor_h
            final_a = a + scor_a

            if final_h > final_a:
                p1 += p
            elif final_h == final_a:
                px += p
            else:
                p2 += p

            if final_h > 0 and final_a > 0:
                gg += p

            if final_h + final_a > 2:
                over25 += p

            rezultate.append((p, final_h, final_a))

    total = p1 + px + p2

    if total > 0:
        p1 /= total
        px /= total
        p2 /= total

    return {
        "1": p1,
        "X": px,
        "2": p2,
        "GG": gg,
        "Over 2.5": over25,
        "scores": sorted(
            rezultate,
            reverse=True
        )[:5]
    }


# ==========================================
# FORMA ECHIPELOR
# ==========================================

def meciuri_terminate(rows):
    return [
        x for x in rows
        if x.get("fixture", {}).get(
            "status", {}
        ).get("short") in ("FT", "AET", "PEN")
        and x.get("goals", {}).get("home") is not None
        and x.get("goals", {}).get("away") is not None
    ]


def forma_echipa(team_id, api_key):
    an = date.today().year

    for sezon in (an, an - 1):
        rows = api_get(
            "fixtures",
            api_key,
            {
                "team": team_id,
                "season": sezon
            }
        )

        rows = meciuri_terminate(rows)

        if len(rows) >= 5:
            return rows[:10]

    raise Exception(
        "Nu există suficiente meciuri istorice."
    )


def medii_echipa(rows, team_id):
    marcate = []
    primite = []

    for m in rows:
        teams = m.get("teams", {})
        goals = m.get("goals", {})

        if teams.get("home", {}).get("id") == team_id:
            marcate.append(goals["home"])
            primite.append(goals["away"])

        elif teams.get("away", {}).get("id") == team_id:
            marcate.append(goals["away"])
            primite.append(goals["home"])

    if not marcate:
        raise Exception("Nu există statistici pentru echipă.")

    return (
        sum(marcate) / len(marcate),
        sum(primite) / len(primite)
    )


def goluri_estimate(home, away, api_key):
    h_rows = forma_echipa(home["id"], api_key)
    a_rows = forma_echipa(away["id"], api_key)

    h_scored, h_conceded = medii_echipa(
        h_rows, home["id"]
    )

    a_scored, a_conceded = medii_echipa(
        a_rows, away["id"]
    )

    lam_h = (h_scored + a_conceded) / 2
    lam_a = (a_scored + h_conceded) / 2

    return (
        max(0.15, min(4, lam_h)),
        max(0.15, min(4, lam_a)),
        len(h_rows),
        len(a_rows)
    )


# ==========================================
# STATISTICI LIVE
# ==========================================

def statistici_live(fixture_id, api_key):
    rows = api_get(
        "fixtures/statistics",
        api_key,
        {"fixture": fixture_id}
    )

    rezultat = {}

    for echipa in rows:
        team_id = echipa.get("team", {}).get("id")
        valori = {}

        for stat in echipa.get("statistics", []):
            valori[stat.get("type")] = stat.get("value")

        rezultat[team_id] = valori

    return rezultat


def valoare_stat(stats, nume):
    try:
        v = stats.get(nume, 0)

        if v is None:
            return 0

        if isinstance(v, str):
            v = v.replace("%", "")

        return float(v)

    except (ValueError, TypeError):
        return 0


def probabilitati_live(
    lam_h,
    lam_a,
    scor_h,
    scor_a,
    minut,
    stats_h=None,
    stats_a=None
):
    ramas = max(0, 90 - minut)

    factor_h = 1.0
    factor_a = 1.0

    if stats_h is not None and stats_a is not None:
        suturi_h = valoare_stat(
            stats_h, "Shots on Goal"
        )
        suturi_a = valoare_stat(
            stats_a, "Shots on Goal"
        )

        factor_h = max(
            0.65,
            min(1.5, 1 + 0.08 * (suturi_h - suturi_a))
        )

        factor_a = max(
            0.65,
            min(1.5, 1 + 0.08 * (suturi_a - suturi_h))
        )

    # Goluri estimate pentru timpul rămas.
    ramase_h = lam_h * ramas / 90 * factor_h
    ramase_a = lam_a * ramas / 90 * factor_a

    return predictie(
        ramase_h,
        ramase_a,
        scor_h,
        scor_a
    )


# ==========================================
# INTERFAȚA
# ==========================================

st.title("⚽ FOOTBALL AI PRO")

st.caption(
    "Analiză statistică și predicții fotbalistice. "
    "Probabilitățile sunt estimări, nu garanții."
)

with st.sidebar:
    st.header("Conectare API")

    api_key = st.text_input(
        "API-FOOTBALL KEY",
        type="password"
    )

    st.caption(
        "Nu publica cheia API și nu o introduce în codul GitHub."
    )


if not api_key:
    st.warning(
        "Introdu cheia API-FOOTBALL în meniul din stânga."
    )
    st.stop()


tab1, tab2, tab3 = st.tabs([
    "MECIURI",
    "LIVE PREDICTIONS",
    "ANALIZĂ MANUALĂ"
])


# ==========================================
# MECIURI NORMALE
# ==========================================

with tab1:
    st.header("Meciuri și predicții")

    data_selectata = st.date_input(
        "Alege data",
        value=date.today()
    )

    if st.button("ÎNCARCĂ MECIURILE"):
        try:
            rows = api_get(
                "fixtures",
                api_key,
                {
                    "date": data_selectata.isoformat(),
                    "timezone": "Europe/Bucharest"
                }
            )

            st.session_state["meciuri"] = rows

        except Exception as e:
            st.error(str(e))

    rows = st.session_state.get("meciuri", [])

    if rows:
        optiuni = {}

        for m in rows:
            home = m["teams"]["home"]
            away = m["teams"]["away"]

            nume = (
                home["name"] + " - " + away["name"]
                + " | " + m["fixture"]["date"][:16]
            )

            optiuni[nume] = m

        ales = st.selectbox(
            "Alege meciul",
            list(optiuni.keys())
        )

        meci = optiuni[ales]

        if st.button("ANALIZEAZĂ MECIUL"):
            try:
                with st.spinner("Calculez probabilitățile..."):
                    home = meci["teams"]["home"]
                    away = meci["teams"]["away"]

                    lh, la, nh, na = goluri_estimate(
                        home, away, api_key
                    )

                    p = predictie(lh, la)

                st.subheader(
                    home["name"] + " - " + away["name"]
                )

                c1, c2, c3 = st.columns(3)

                c1.metric("1", f"{p['1'] * 100:.1f}%")
                c2.metric("X", f"{p['X'] * 100:.1f}%")
                c3.metric("2", f"{p['2'] * 100:.1f}%")

                st.write(
                    f"Goluri estimate: {lh:.2f} - {la:.2f}"
                )

                c1, c2 = st.columns(2)

                c1.metric("GG", f"{p['GG'] * 100:.1f}%")
                c2.metric(
                    "Over 2.5",
                    f"{p['Over 2.5'] * 100:.1f}%"
                )

                st.write("Scoruri estimate")

                st.dataframe(
                    pd.DataFrame([
                        {
                            "Scor": f"{h}-{a}",
                            "Probabilitate": f"{prob * 100:.1f}%"
                        }
                        for prob, h, a in p["scores"]
                    ]),
                    use_container_width=True,
                    hide_index=True
                )

                st.caption(
                    f"Istoric analizat: {nh} meciuri gazde, "
                    f"{na} meciuri oaspeți."
                )

            except Exception as e:
                st.error(str(e))


# ==========================================
# LIVE PREDICTIONS
# ==========================================

with tab2:
    st.header("🔴 LIVE PREDICTIONS")

    st.caption(
        "Apasă butonul pentru a prelua meciurile "
        "aflate în desfășurare."
    )

    if st.button(
        "ACTUALIZEAZĂ MECIURILE LIVE",
        type="primary"
    ):
        try:
            live_rows = api_get(
                "fixtures",
                api_key,
                {"live": "all"}
            )

            st.session_state["live_rows"] = live_rows

        except Exception as e:
            st.error(str(e))

    live_rows = st.session_state.get("live_rows", [])

    if not live_rows:
        st.info(
            "Nu sunt meciuri LIVE afișate. "
            "Actualizează lista în timpul meciurilor."
        )

    else:
        optiuni_live = {}

        for m in live_rows:
            home = m["teams"]["home"]
            away = m["teams"]["away"]

            scor = m.get("goals", {})
            minut = m["fixture"]["status"].get("elapsed")

            nume = (
                home["name"] + " "
                + str(scor.get("home")) + " - "
                + str(scor.get("away")) + " "
                + away["name"] + " | "
                + str(minut or 0) + "'"
            )

            optiuni_live[nume] = m

        ales_live = st.selectbox(
            "Alege meciul LIVE",
            list(optiuni_live.keys())
        )

        meci_live = optiuni_live[ales_live]

        fixture = meci_live["fixture"]
        home = meci_live["teams"]["home"]
        away = meci_live["teams"]["away"]

        scor = meci_live.get("goals", {})

        scor_h = scor.get("home") or 0
        scor_a = scor.get("away") or 0

        minut = fixture["status"].get("elapsed") or 0

        st.subheader(
            home["name"] + " - " + away["name"]
        )

        c1, c2, c3 = st.columns(3)

        c1.metric("GAZDE", scor_h)
        c2.metric("MINUT", str(minut) + "'")
        c3.metric("OASPEȚI", scor_a)

        if st.button("CALCULEAZĂ PREDICȚIA LIVE"):
            try:
                with st.spinner(
                    "Preiau istoricul și statisticile..."
                ):
                    lh, la, _, _ = goluri_estimate(
                        home, away, api_key
                    )

                    stats = statistici_live(
                        fixture["id"], api_key
                    )

                    stats_h = stats.get(home["id"])
                    stats_a = stats.get(away["id"])

                    p = probabilitati_live(
                        lh,
                        la,
                        scor_h,
                        scor_a,
                        minut,
                        stats_h,
                        stats_a
                    )

                st.success("Analiza LIVE a fost calculată.")

                c1, c2, c3 = st.columns(3)

                c1.metric("1", f"{p['1'] * 100:.1f}%")
                c2.metric("X", f"{p['X'] * 100:.1f}%")
                c3.metric("2", f"{p['2'] * 100:.1f}%")

                c1, c2 = st.columns(2)

                c1.metric("GG", f"{p['GG'] * 100:.1f}%")
                c2.metric(
                    "Over 2.5",
                    f"{p['Over 2.5'] * 100:.1f}%"
                )

                st.subheader("Scoruri finale estimate")

                st.dataframe(
                    pd.DataFrame([
                        {
                            "Scor final": f"{h}-{a}",
                            "Probabilitate": f"{prob * 100:.1f}%"
                        }
                        for prob, h, a in p["scores"]
                    ]),
                    use_container_width=True,
                    hide_index=True
                )

                st.caption(
                    "Model orientativ: istoric, scor curent, "
                    "minute rămase și șuturi pe poartă. "
                    "Statisticile lipsă nu sunt inventate."
                )

            except Exception as e:
                st.error(
                    "Analiza LIVE nu a putut fi calculată: "
                    + str(e)
                )


# ==========================================
# ANALIZĂ MANUALĂ
# ==========================================

with tab3:
    st.header("Analiză manuală")

    c1, c2 = st.columns(2)

    with c1:
        nume_h = st.text_input("Echipa gazdă")
        goluri_h = st.number_input(
            "Media golurilor gazdelor",
            0.0, 5.0, 1.4
        )
        primite_h = st.number_input(
            "Media golurilor primite de gazde",
            0.0, 5.0, 1.1
        )

    with c2:
        nume_a = st.text_input("Echipa oaspete")
        goluri_a = st.number_input(
            "Media golurilor oaspeților",
            0.0, 5.0, 1.2
        )
        primite_a = st.number_input(
            "Media golurilor primite de oaspeți",
            0.0, 5.0, 1.3
        )

    if st.button("CALCULEAZĂ"):
        lh = (goluri_h + primite_a) / 2
        la = (goluri_a + primite_h) / 2

        p = predictie(lh, la)

        st.subheader(nume_h + " - " + nume_a)

        c1, c2, c3 = st.columns(3)

        c1.metric("1", f"{p['1'] * 100:.1f}%")
        c2.metric("X", f"{p['X'] * 100:.1f}%")
        c3.metric("2", f"{p['2'] * 100:.1f}%")

        st.write(
            f"GG: {p['GG'] * 100:.1f}%"
        )

        st.write(
            f"Over 2.5: {p['Over 2.5'] * 100:.1f}%"
        )

st.divider()

st.caption(
    "FOOTBALL AI PRO | Model statistic experimental. "
    "Predicțiile nu garantează rezultatele."
        )
