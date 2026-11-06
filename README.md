# FOOTBALL AI PRO v2

Aplicație Streamlit pentru analiză fotbalistică folosind API-FOOTBALL v3.

## Instalare locală
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Publicare în Streamlit Community Cloud
- Repository: contul GitHub / FOOTBALL-AI-PRO
- Branch: main
- Main file path: app.py

## Utilizare
1. Introdu cheia API-FOOTBALL în câmpul secret din bara laterală.
2. Alege data și apasă „Încarcă meciurile”.
3. Selectează un meci și apasă „Analizează meciul selectat”.
4. Pentru test istoric, folosește ID-ul competiției și sezonul în tabul „Validare istorică”.

## Notă privind datele și limitele
- Accesul la endpoint-uri depinde de abonamentul API și de acoperirea competiției/sezonului.
- Modelul Poisson este o estimare statistică simplificată, nu o garanție.
- xG și cornere nu sunt fabricate; nu sunt incluse în modelul propriu în această versiune.
- Cheia API nu se introduce în fișiere și nu se comite în GitHub.
