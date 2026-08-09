# Tasks — Dashboard Modernization

## Task 1: Overview page — dense KPI strip + sector table
- [x] Replace KPI grid cards with a single-row numeric strip (NAV, P&L daily/MTD/YTD, gross, net, longs, shorts, drawdown)
- [x] Add sector exposure table (one row per active sector: net %, # names, daily P&L contribution)
- [x] Add factor beta row as colored chips
- [x] Remove equity curve from overview (move to Book tab)
- [x] Remove Action Required panel redundancy (recommendations have their own tab)
- [x] Remove Agent Consensus widget (IC Debate tab covers this)

## Task 2: Recommendations page — trade ticket format
- [x] Already implemented this session — verify format after full run
- [x] Add sort-by-conviction default
- [x] Add sector filter dropdown

## Task 3: Book page — ratio-driven sortable table
- [x] Simplify to pure table (remove portfolio P&L chart above — move to separate equity sub-section)
- [x] Ensure columns are: Pair, Dir, Entry Ratio, Current Ratio, Peak, Pair P&L%, Dist-Peak%, Trail%, Days, Size%, Sector
- [x] Add summary row (totals: gross, net, avg P&L)
- [x] Add equity curve below table (moved from overview)
- [x] Tighten row height and padding for density

## Task 4: Blotter — linked IC context
- [x] Already stores debate/tech/risk in journal entries (implemented this session)
- [x] Add date grouping headers
- [x] Show Tech Score badge and Risk Decision badge inline on each row
- [x] Add cumulative P&L column for closed trades

## Task 5: CSS tightening
- [x] Reduce metric-card padding from 20px to 14px globally
- [x] Enforce font-variant-numeric: tabular-nums on all number cells
- [x] Remove hover translateY effects on data tables (keep on action cards only)
- [x] Tighten section-title margin from 16px to 10px
- [x] Reduce .pending-card padding from 24px to 18px
- [x] Make all timestamps show HH:MM ET format (not full ISO)

## Task 6: Run IC Sweep integration
- [x] Verify loading overlay updates live with phase progress
- [x] Confirm proposals → debate → tech → risk → orders pipeline populates all tabs
- [x] Test approve/pass flow end-to-end

## Task 7: Final polish
- [x] Regenerate dashboard.py with all changes
- [x] Verify serve.py regeneration produces correct output
- [x] Test mobile layout (functional, not primary)
- [-] Push to git
