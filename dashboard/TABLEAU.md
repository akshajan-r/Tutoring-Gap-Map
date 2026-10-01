# Building the dashboard in Tableau Public

Tableau Public can't connect to SQLite or Postgres, so the pipeline exports
flat files: `python -m tgm all` writes them to `outputs/dashboard_data/`.

| File | Grain | Use it for |
|---|---|---|
| `schools.csv` | school × year (state-funded mainstream) | the map, any view that should respond to the school-type filter |
| `local_authorities.csv` | LA × year | rankings, trends, `rank_change`, `trend` |
| `beating_the_odds.csv` | one row per school (latest year) | the "schools to learn from" table |
| `national.csv` | year | England benchmark line |

`tutoring_gap_map.xlsx` has the same four tables as sheets, so one connection covers everything.

The target layout (the HTML preview at `outputs/tutoring_gap_map.html` is a working mock-up of it):

```
┌───────────────────────────────────────────────────────────────────────────┐
│ Year ▾   Region ▾   School type ▾   Measure ▾ (parameter)                 │
├──────────┬──────────┬──────────┬──────────────────────────────────────────┤
│ Disadv.  │ Non-dis. │ Gap      │ Schools beating the odds                 │  KPI tiles
├──────────┴──────────┴──────────┼──────────────────────────────────────────┤
│                                │  Top 15 LAs by gap (bar)                 │
│   Map: LA circles (size = disadv. pupils, colour = gap)                   │
│        + beating-the-odds schools as green dots                           │
├────────────────────────────────┼──────────────────────────────────────────┤
│  Beating the odds (table)      │  Gap over time: selected LA vs England   │
└────────────────────────────────┴──────────────────────────────────────────┘
```

## 1. Connect

1. Tableau Public → **Connect → Microsoft Excel** → `tutoring_gap_map.xlsx`.
2. Drag `schools` onto the canvas. Create separate data sources (Data → New Data
   Source) for `local_authorities`, `beating_the_odds` and `national`. Keeping
   them separate avoids accidental many-to-many joins.
3. In each source set `latitude` / `longitude` to **Geographic Role → Latitude/Longitude**
   and `academic_year`, `region`, `school_type`, `la_name` to Dimension.

## 2. Calculated fields (in the `schools` source)

These rebuild the pupil-weighted LA figures from school rows, so the map and
tiles respond to the **school type** filter. `local_authorities.csv` can't do
that, because it is pre-aggregated across all school types.

```
// Disadv pupils (published)
IF NOT ISNULL([att8_disadv]) THEN [n_disadv] END

// Disadv Att8 (weighted)
SUM(IF NOT ISNULL([att8_disadv]) THEN [n_disadv] * [att8_disadv] END)
  / SUM([Disadv pupils (published)])

// Non-disadv Att8 (weighted)
SUM(IF NOT ISNULL([att8_nondisadv]) THEN ([total_pupils] - [n_disadv]) * [att8_nondisadv] END)
  / SUM(IF NOT ISNULL([att8_nondisadv]) THEN [total_pupils] - [n_disadv] END)

// Gap vs national          (headline measure)
AVG([national_att8_nondisadv]) - [Disadv Att8 (weighted)]

// Gap within area
[Non-disadv Att8 (weighted)] - [Disadv Att8 (weighted)]

// Gap in grades per subject
[Gap vs national] / 10

// Scale of need
SUM([Disadv pupils (published)]) * [Gap vs national] / 10
```

Measure switcher: create a string parameter **Measure** with values
`Gap vs national`, `Gap within area`, `Scale of need`, then:

```
// Selected measure
CASE [Measure]
  WHEN "Gap vs national" THEN [Gap vs national]
  WHEN "Gap within area" THEN [Gap within area]
  WHEN "Scale of need"   THEN [Scale of need]
END
```

## 3. Sheets

**Map: gap by LA** (`schools` source)
- Marks: Circle. Rows `AVG(latitude)`, Columns `AVG(longitude)`. Detail: `la_name`, `region`.
- Size: `SUM([Disadv pupils (published)])`. Colour: `[Selected measure]`, sequential
  single-hue blue, 5 stepped colours. Use a single hue, not red-green.
- Tooltip: LA, region, gap vs national, gap within area, disadvantaged Att8, pupils.
- Map → Background Maps → Light. Layer the beating-the-odds schools on top as a
  second marks layer (Tableau 2020.4+: drag `beating_the_odds` lat/lon onto the
  map as **Add a Marks Layer**), green circles, filtered to `evidence` starts with "Consistent".
- For a filled (choropleth) map instead of circles, download the ONS
  "Counties and Unitary Authorities" boundaries (BUC GeoJSON) from
  geoportal.statistics.gov.uk, add it as a spatial file and relate on
  `la_name` = `CTYUA name`. Most names match exactly. Check the handful that
  don't (e.g. "Bristol, City of", "Herefordshire, County of").

**Top 15 areas** (`local_authorities` source, or `schools` for type-aware)
- Rows `la_name` sorted by `[Selected measure]` descending; Columns the measure; Filter
  `la_name` → Top 15 by the measure. One colour for all bars.
- Tooltip: `rank_gap_vs_national` of `n_las_in_year`, `change_gap_vs_national`, `trend`.

**Gap over time** (`local_authorities` + `national`)
- Columns `academic_year` (discrete, sorted by `year_start`). Rows `gap_vs_national`.
- Dual-source: add `national.att8_gap` as the England line. Same axis, **not** a
  dual axis (it's the same measure, the national version).
- Filter `la_name` from the map/bar selection with a dashboard filter action.
- Annotate the gap between 2018-19 and 2021-22 ("no exams 2020, 2021").

**Beating the odds** (`beating_the_odds` source)
- Text table: `school_name`, `la_name`, `school_type`, `imd_decile`, `pct_disadv`,
  `att8_disadv`, `att8_disadv_expected`, `years_beating_odds` / `years_in_model`, `evidence`.
- Sort by `years_beating_odds` desc, then `avg_residual_z` desc.
- Filter `evidence` (default: Consistent (2+ years)).

**KPI tiles**: one sheet each, Text marks, big number: `[Disadv Att8 (weighted)]`,
`AVG([national_att8_nondisadv])`, `[Gap vs national]`, `COUNTD(beating_the_odds.lineage_id)`.

## 4. Filters and actions

- **Year**: `academic_year`, single value (dropdown), default the latest year.
  Apply to *All using related data sources* (the field name is shared, so
  Tableau blends on it). `beating_the_odds` has no year; it shows each school's latest.
- **Region**: `region`, apply to all using related data sources.
- **School type**: `school_type`, applies to the `schools` and `beating_the_odds` sheets.
- Dashboard actions: **Filter** from the map and bar chart to the trend chart (`la_name`),
  **Highlight** on `la_name` between the map and bars.

## 5. Publish

File → Save to Tableau Public. Put a caption under the title with the sources and
the method notes from the README ("How the measures work" and "Caveats").
