# FOOTBALL AI PRO — versiunea 1.0

## Pornire pe calculator
1. Instalează Python 3.10 sau mai nou.
2. Deschide terminalul în folderul proiectului.
3. Rulează:
   ```bash
   pip install -r requirements.txt
   streamlit run app.py
   ```
4. Aplicația se deschide în browser.

## Date automate
Pentru programul meciurilor și mediile echipelor este necesară o cheie API-FOOTBALL:
https://www.api-football.com/

Introdu cheia în câmpul din bara laterală. Aplicația nu o salvează în fișier.
Disponibilitatea statisticilor depinde de competiție și planul API.

## Fără cheie
Fila „Analiză manuală” funcționează fără cont/API. Introdu mediile pe meci:
- gazde: goluri marcate și primite acasă;
- oaspeți: goluri marcate și primite în deplasare;
- mediile ligii pentru gazde și oaspeți.

## Limitări
Versiunea 1.0 folosește un model Poisson simplificat, cu rate normalizate la mediile ligii. Nu verifică automat accidentări, suspendări, xG, forma ultimelor partide sau cote. Datele API pot fi incomplete. Probabilitățile sunt estimări, nu certitudini și nu garantează câștiguri.
