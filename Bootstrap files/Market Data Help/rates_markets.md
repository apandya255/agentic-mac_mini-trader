# Rates Markets Map — desk/rates_markets.md

Per-market conventions, official sources, and fetcher status for the rates sleeve. Each macro seat owns its region's rows; a market is TRADEABLE only when its Fetcher column says LIVE (validated end-to-end per feed doctrine). Instrument-tier rules and the whole-curve discipline live in desk/universe.md and desk/rates_method.md — this file is the access layer.

Tier key: 1 = exchange futures w/ public settlements · 2 = govt benchmark yields off official daily source · 3 = short-tenor OIS vs published O/N fixings.

| Market | Tier | Instrument / quote | Day count | Official source | Fetcher | Status | Owner |
|--------|------|--------------------|-----------|-----------------|---------|--------|-------|
| US | 1 | ZT/ZF/ZN/TN/ZB (price); full par curve | ACT/ACT | CME via yfinance (=F); Treasury.gov daily par CSV | prices.py / curves.py | =F LIVE at v1; curve v1.2 | North America |
| US OIS | 3 | SOFR OIS, short tenor | ACT/360 | NY Fed SOFR fixings | curves.py | v1.2 | North America |
| Germany | 1 | Schatz/Bobl/Bund | ACT/ACT | Eurex daily settlements | curves.py | v1.2 | Western Europe |
| UK | 1/3 | Gilt futures; SONIA OIS | ACT/365F | ICE settlements; BoE SONIA | curves.py | v1.2 | Western Europe |
| Japan | 1/3 | JGB futures; TONA OIS | ACT/365F | JPX/OSE; BoJ TONA | curves.py | v1.2 | Asia |
| Brazil | 1 | DI1 (ODxNN, rate quote; PU = 100,000/(1+i)^(du/252)) | BUS/252 | B3 daily settlement file | curves.py | v1.2 — first EM build | LatAm |
| Mexico | 1/3 | TIIE / F-TIIE futures; F-TIIE OIS | ACT/360 | MexDer settlements; Banxico F-TIIE fixing | curves.py | v1.2 (mind the F-TIIE splice) | LatAm |
| Colombia | 3 | IBR OIS 1M/3M — settles vs realized compounded fixings; no intraperiod MTM | ACT/360 | BanRep daily IBR fixing | curves.py | v1.2 (fixings only — honest today) | LatAm |
| Poland | 2/3 | POLGB 10y benchmark; POLONIA OIS | ACT/ACT | MinFin/NBP | curves.py | v1.2 | CEEMEA |
| Hungary | 2 | HGB benchmark yields | ACT/ACT | ÁKK daily reference yields | curves.py | v1.2 | CEEMEA |
| Czechia | 2 | CZGB benchmarks | ACT/ACT | MinFin/CNB | curves.py | v1.2 | CEEMEA |
| South Africa | 2 | SAGB benchmarks | ACT/365F | JSE / SARB | curves.py | v1.3 | CEEMEA |
| China | 2 | CGB curve | ACT/ACT | ChinaBond daily official curve | curves.py | v1.3 | Asia |
| India | 2 | G-sec valuations | ACT/ACT | FBIL daily | curves.py | v1.3 | Asia |
| Korea | 2 | KTB yields | ACT/365F | KOFIA | curves.py | v1.3 | Asia |
| Thailand | 2 | ThaiBMA daily marks | ACT/365F | ThaiBMA | curves.py | v1.3 | Asia |

Rollout law: LatAm + CEE first, then DM completion, then Asia. A seat proposing a rates trade in a non-LIVE market expresses via proxy (labeled) or waits — never improvises a mark. Day counts to be verified against each market's docs at fetcher build, not trusted from this table.
