# Building the dashboard in Power BI

Power BI Desktop can read the database directly, or the exported CSVs.

- **SQLite**: Get Data → ODBC (install the SQLite ODBC driver), then pick the
  `dash_schools`, `dash_local_authorities`, `v_beating_the_odds` and
  `v_national_trends` views.
- **Postgres**: Get Data → PostgreSQL database, the same four views.
- **CSV**: Get Data → Text/CSV for each file in `outputs/dashboard_data/`.

Rename the tables `schools`, `local_authorities`, `beating_the_odds`, `national`
so the DAX in [`measures.dax`](measures.dax) works as written.

## Model

Create small dimension tables so one slicer filters every table:

```
Years   = DISTINCT(UNION(DISTINCT(schools[academic_year]), DISTINCT(local_authorities[academic_year])))
Regions = DISTINCT(UNION(DISTINCT(schools[region]), DISTINCT(local_authorities[region])))
```

Relationships (single direction, from dimension to fact):
- `Years[academic_year]` → `schools`, `local_authorities`, `national`
- `Regions[region]` → `schools`, `local_authorities`, `beating_the_odds`

Sort `academic_year` by `year_start` (Column tools → Sort by column).

## Measures

Paste in [`measures.dax`](measures.dax). The key ones:
- `Disadv Att8`: pupil-weighted, only over schools where the figure was published
- `Gap vs national` (the headline) and `Gap within area`
- `Scale of need`: disadvantaged pupils × grades behind per subject
- `Selected measure`: driven by a field parameter or a disconnected table for the measure switcher

## Visuals

| Visual | Fields |
|---|---|
| **Map** (Azure Maps or Map) | Latitude/Longitude: `local_authorities[latitude]`, `[longitude]` (or average school lat/lon by `la_name` from `schools`, which responds to the school-type slicer). Bubble size: `Disadv pupils`. Colour: `Gap vs national`, sequential, one hue. Add a second layer for `beating_the_odds` lat/lon in green. |
| **Bar chart**: largest gaps | Axis `la_name`, value `Gap vs national`, Top N = 15 visual filter |
| **Line chart**: trend | X `academic_year`, Y `Gap vs national` for the selected LA plus `national[att8_gap]` as a second line on the **same** axis |
| **Table**: beating the odds | `school_name`, `la_name`, `imd_decile`, `pct_disadv`, `att8_disadv`, `att8_disadv_expected`, `years_beating_odds`, `evidence` |
| **Cards** | `Disadv Att8`, `National non-disadv Att8`, `Gap vs national`, `Schools beating the odds` |
| **Slicers** | `Years[academic_year]` (single select), `Regions[region]`, `schools[school_type]` |

Edit interactions so selecting an LA on the map or bar chart filters the trend line.
