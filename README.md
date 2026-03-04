# colectatron8000

**Volunteer shift scheduler for fundraising collections.**

colectatron8000 is an operations research optimization tool that assigns
volunteers to street corners across multiple dates and time slots for a
fundraising collection. It uses a [Gurobi](https://www.gurobi.com/) integer
programming model to respect volunteer availability, per-location time-block
capacities, and individual shift limits (minimum and maximum number of shifts
per volunteer).

## Project structure

```
colectatron8000/
├── data/                   # Input datasets and output results
├── src/
│   ├── data_processing.py  # Parse volunteer availability and location capacities
│   ├── solver.py           # Gurobi optimization model
│   └── main.py             # Entry point: load data → solve → export
├── requirements.txt
└── README.md
```

## Prerequisites

* Python 3.9 or later
* A valid [Gurobi licence](https://www.gurobi.com/downloads/end-user-license-agreement-academic/)
  (free academic licences are available)

Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Input data format

Place the following files inside the `data/` directory before running the model.

### `availability.csv` / `availability.xlsx`

One row per volunteer × date × time-slot combination that the volunteer is
available for.  Required columns:

| Column      | Description                                     |
|-------------|-------------------------------------------------|
| `volunteer` | Unique volunteer identifier (name or ID)        |
| `date`      | Date of the collection shift (YYYY-MM-DD)       |
| `slot`      | Time-slot label (e.g. `morning`, `afternoon`)   |
| `location`  | Street corner / collection point identifier     |

### `capacities.csv` / `capacities.xlsx`

One row per location × date × time-slot combination, defining how many
volunteers can be assigned simultaneously.  Required columns:

| Column      | Description                                              |
|-------------|----------------------------------------------------------|
| `location`  | Street corner / collection point identifier              |
| `date`      | Date of the collection shift (YYYY-MM-DD)                |
| `slot`      | Time-slot label                                          |
| `capacity`  | Maximum number of volunteers allowed in this block       |

### `volunteer_limits.csv` / `volunteer_limits.xlsx` *(optional)*

Override the default minimum/maximum shift limits per volunteer.  Required
columns:

| Column      | Description                            |
|-------------|----------------------------------------|
| `volunteer` | Volunteer identifier                   |
| `min_shifts`| Minimum number of shifts to assign     |
| `max_shifts`| Maximum number of shifts to assign     |

## Running the model

```bash
python src/main.py \
    --availability  data/availability.csv \
    --capacities    data/capacities.csv \
    --output        data/assignments.csv \
    [--limits       data/volunteer_limits.csv] \
    [--min-shifts   1] \
    [--max-shifts   3]
```

The solver writes the resulting assignment table to the path given by
`--output` (default: `data/assignments.csv`).

### Example

```bash
python src/main.py \
    --availability data/availability.csv \
    --capacities   data/capacities.csv \
    --output       data/assignments.csv
```

## Output

The output CSV contains one row per assigned shift:

| Column      | Description                         |
|-------------|-------------------------------------|
| `volunteer` | Volunteer identifier                |
| `date`      | Date of the assigned shift          |
| `slot`      | Time-slot of the assigned shift     |
| `location`  | Assigned street corner              |

## Licence

MIT
