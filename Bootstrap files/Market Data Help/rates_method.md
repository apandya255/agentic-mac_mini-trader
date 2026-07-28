# Rates Methodology — desk/rates_method.md
Loaded alongside a macro mandate whenever a rates idea is worked. The unit of analysis is the CURVE, never a single tenor.

## 1. Pull the whole curve
Fetch every available point per market (all DI1 maturities from the B3 file, full benchmark set from the debt agency, full UST par curve from Treasury.gov daily CSV). A rates idea built off one tenor without the strip is incomplete work — reject it at debate.

## 2. Compute, every time
- Spot rate per tenor; key forwards the curve supports (1y1y, 2y1y, 5y5y).
- Market-implied policy path from the front contracts / OIS strip vs. the seat's OWN central bank path — the divergence IS the trade candidate.
- Carry + rolldown per point, 3m horizon. Know where the curve pays you to wait and where it bleeds.
- Slope (2s10s, 5s10s, front/red) and curvature (flys) vs. ≥1y history, in z-scores.

## 3. Choose the point and the structure — and argue it
"Most interesting part of the curve" is a conclusion, not an assertion. The pitch must state why this point/structure beats the alternatives:
- **Outright** (REC/PAY one point): view on level; pick the tenor with max house-vs-market divergence per unit of carry bleed.
- **Steepener/flattener** (DV01-neutral): view on shape; isolates the path/term-premium call from the level call.
- **Fly** (50/50 DV01 wings): RV on curvature; needs the z-score and a normalization catalyst, not just "it's stretched."
A level view expressed as an outright at the wrong point is a worse trade than the same view at the right point — tenor selection is alpha.

## 4. Conventions
- Curve trades (slope/fly) = ONE position, one slot. Quote the spread: `REC ODF27 / PAY ODF29 @ -85bps | tgt -60 | stop -100 | DV01/leg $X`. Stop/target in spread terms.
- Carry + roll appears in every rates pitch. A receiver fighting negative carry needs the timing argument stated, not implied.
- Marking, P&L math, and per-market sources per desk/universe.md tiers and desk/rates_markets.md.
