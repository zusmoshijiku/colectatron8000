"""
solver.py
~~~~~~~~~
Gurobi integer-programming model for volunteer shift assignment.

The model assigns volunteers to (date, slot, location) time-blocks while
respecting:
  * Volunteer availability: a volunteer can only be assigned to a block
    for which they declared availability.
  * Location capacity: the number of volunteers in a block cannot exceed
    the block's capacity.
  * Volunteer shift limits: each volunteer is assigned at least min_shifts
    and at most max_shifts in total.
  * Conflict-free assignment: a volunteer is assigned to at most one location
    per (date, slot) combination.

Objective
---------
Maximise the total number of filled volunteer-block slots (weighted equally),
subject to all constraints. This encourages full coverage of available
capacity while honouring all hard constraints.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

import pandas as pd

try:
    import gurobipy as gp
    from gurobipy import GRB
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "gurobipy is required to run the solver. "
        "Install it with: pip install gurobipy"
    ) from exc


def build_and_solve(
    availability: pd.DataFrame,
    capacities: pd.DataFrame,
    volunteers: list[str],
    blocks: list[tuple],
    volunteer_min: dict[str, int],
    volunteer_max: dict[str, int],
    time_limit: Optional[float] = 300.0,
    mip_gap: float = 0.01,
) -> pd.DataFrame:
    """Build the Gurobi model, solve it, and return the assignment table.

    Parameters
    ----------
    availability   : DataFrame with columns (volunteer, date, slot, location)
    capacities     : DataFrame with columns (location, date, slot, capacity)
    volunteers     : list of volunteer IDs
    blocks         : list of (date, slot, location) tuples
    volunteer_min  : {volunteer: min_shifts}
    volunteer_max  : {volunteer: max_shifts}
    time_limit     : solver time limit in seconds (None = no limit)
    mip_gap        : relative MIP optimality gap tolerance

    Returns
    -------
    pd.DataFrame with columns (volunteer, date, slot, location) for every
    assigned shift.  Returns an empty DataFrame if the model is infeasible.
    """
    # -----------------------------------------------------------------------
    # Pre-process lookup structures
    # -----------------------------------------------------------------------

    # Set of valid (volunteer, date, slot, location) combos
    avail_set: set[tuple] = set(
        availability.itertuples(index=False, name=None)
    )

    # Capacity lookup: (date, slot, location) -> int
    cap_lookup: dict[tuple, int] = {
        (row.date, row.slot, row.location): row.capacity
        for row in capacities.itertuples(index=False)
    }

    # -----------------------------------------------------------------------
    # Build model
    # -----------------------------------------------------------------------
    model = gp.Model("colectatron8000")
    model.setParam("OutputFlag", 1)
    if time_limit is not None:
        model.setParam("TimeLimit", time_limit)
    model.setParam("MIPGap", mip_gap)

    # Decision variables: x[v, d, s, l] ∈ {0, 1}
    # 1 if volunteer v is assigned to location l on date d in slot s
    x: dict[tuple, gp.Var] = {}
    for v, d, s, l in avail_set:
        if (d, s, l) in cap_lookup:  # only if the block has a capacity entry
            x[v, d, s, l] = model.addVar(vtype=GRB.BINARY, name=f"x_{v}_{d}_{s}_{l}")

    if not x:
        print("No feasible variable combinations found. Check input data.")
        return pd.DataFrame(columns=["volunteer", "date", "slot", "location"])

    model.update()

    # -----------------------------------------------------------------------
    # Objective: maximise total assignments
    # -----------------------------------------------------------------------
    model.setObjective(gp.quicksum(x.values()), GRB.MAXIMIZE)

    # -----------------------------------------------------------------------
    # Constraints
    # -----------------------------------------------------------------------

    # 1. Capacity: sum of volunteers in a block ≤ capacity
    block_vars: dict[tuple, list[gp.Var]] = defaultdict(list)
    for (v, d, s, l), var in x.items():
        block_vars[d, s, l].append(var)

    for (d, s, l), vars_in_block in block_vars.items():
        cap = cap_lookup.get((d, s, l), 0)
        model.addConstr(
            gp.quicksum(vars_in_block) <= cap,
            name=f"cap_{d}_{s}_{l}",
        )

    # 2. No double-booking: each volunteer in at most one location per (date, slot)
    slot_vars: dict[tuple, list[gp.Var]] = defaultdict(list)
    for (v, d, s, l), var in x.items():
        slot_vars[v, d, s].append(var)

    for (v, d, s), vars_in_slot in slot_vars.items():
        model.addConstr(
            gp.quicksum(vars_in_slot) <= 1,
            name=f"nodup_{v}_{d}_{s}",
        )

    # 3. Minimum shifts per volunteer (soft: skipped if infeasible)
    volunteer_vars: dict[str, list[gp.Var]] = defaultdict(list)
    for (v, d, s, l), var in x.items():
        volunteer_vars[v].append(var)

    for v in volunteers:
        v_vars = volunteer_vars.get(v, [])
        if not v_vars:
            continue
        min_s = volunteer_min.get(v, 0)
        max_s = volunteer_max.get(v, len(v_vars))
        if min_s > 0:
            model.addConstr(
                gp.quicksum(v_vars) >= min_s,
                name=f"min_shifts_{v}",
            )
        model.addConstr(
            gp.quicksum(v_vars) <= max_s,
            name=f"max_shifts_{v}",
        )

    # -----------------------------------------------------------------------
    # Solve
    # -----------------------------------------------------------------------
    model.optimize()

    status = model.Status
    if status in (GRB.INFEASIBLE, GRB.INF_OR_UNBD):
        print(f"Model is infeasible or unbounded (status={status}).")
        _try_compute_iis(model)
        return pd.DataFrame(columns=["volunteer", "date", "slot", "location"])

    if status not in (GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.SUBOPTIMAL):
        print(f"Solver finished with unexpected status: {status}")
        return pd.DataFrame(columns=["volunteer", "date", "slot", "location"])

    # -----------------------------------------------------------------------
    # Extract solution
    # -----------------------------------------------------------------------
    rows = []
    for (v, d, s, l), var in x.items():
        if var.X > 0.5:
            rows.append({"volunteer": v, "date": d, "slot": s, "location": l})

    result = pd.DataFrame(rows, columns=["volunteer", "date", "slot", "location"])
    result = result.sort_values(["date", "slot", "location", "volunteer"]).reset_index(
        drop=True
    )
    return result


def _try_compute_iis(model: gp.Model) -> None:
    """Attempt to compute an IIS for debugging infeasible models."""
    try:
        model.computeIIS()
        print("IIS written to /tmp/colectatron_iis.ilp")
        model.write("/tmp/colectatron_iis.ilp")
    except gp.GurobiError:
        pass
