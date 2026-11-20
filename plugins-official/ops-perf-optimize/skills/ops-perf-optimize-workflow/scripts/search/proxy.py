# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Small-sample axis-aware proxy over the verified workflow history.

Ridge regression on log(candidate/reference) with numeric axis values and
mechanism one-hot features. This is intentionally simple: it is a cold-start
model, not a replacement for device measurement.
"""

from __future__ import annotations

import math
import statistics

from . import prior


def _numeric_axes(rows):
    names = set()
    for row in rows:
        for key, value in row.get("axes", {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                names.add(key)
    return sorted(names)


def _solve(matrix, vector):
    n = len(vector)
    a = [list(matrix[i]) + [vector[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        if abs(a[pivot][col]) < 1e-12:
            continue
        a[col], a[pivot] = a[pivot], a[col]
        divisor = a[col][col]
        for j in range(col, n + 1):
            a[col][j] /= divisor
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            for j in range(col, n + 1):
                a[row][j] -= factor * a[col][j]
    return [a[i][n] for i in range(n)]


def fit(rows, *, soc=None, ridge=1.0):
    rows = [row for row in rows if isinstance(row.get("ratio"), (int, float))]
    if not rows:
        raise ValueError("proxy needs measured rows")
    axis_names = _numeric_axes(rows)
    mechanisms = sorted({row["mechanism"] for row in rows})
    features = []
    targets = []
    for row in rows:
        vector = [1.0]
        for name in axis_names:
            value = row.get("axes", {}).get(name, 0.0)
            vector.append(float(value))
        vector.extend(
            1.0 if row["mechanism"] == mechanism else 0.0 for mechanism in mechanisms
        )
        features.append(vector)
        targets.append(math.log(float(row["ratio"])))
    width = len(features[0])
    xtx = [[0.0] * width for _ in range(width)]
    xty = [0.0] * width
    for vector, target in zip(features, targets):
        for i in range(width):
            xty[i] += vector[i] * target
            for j in range(width):
                xtx[i][j] += vector[i] * vector[j]
    for i in range(1, width):
        xtx[i][i] += ridge
    weights = _solve(xtx, xty)
    residuals = [
        math.log(float(row["ratio"])) - sum(w * x for w, x in zip(weights, vector))
        for row, vector in zip(rows, features)
    ]
    return {
        "axis_names": axis_names,
        "mechanisms": mechanisms,
        "weights": weights,
        "sigma": statistics.stdev(residuals) if len(residuals) > 1 else 1.0,
        "n": len(rows),
    }


def predict(model, row):
    vector = [1.0]
    for name in model["axis_names"]:
        value = row.get("axes", {}).get(name, 0.0)
        vector.append(float(value))
    vector.extend(
        1.0 if row["mechanism"] == mechanism else 0.0
        for mechanism in model["mechanisms"]
    )
    log_ratio = sum(w * x for w, x in zip(model["weights"], vector))
    return {
        "log_ratio": log_ratio,
        "speedup": math.exp(-log_ratio),
        "sigma": model["sigma"],
    }


def rank(history, nodes, *, soc, beta=0.5, weights=None):
    weights = weights or {"cost": 0.3, "risk": 0.3}
    rows = prior.iter_rows(history, soc=soc)
    if not rows:
        return prior.rank_nodes(history, nodes, soc=soc)
    model = fit(rows)
    ranked = []
    for node in nodes:
        row = {
            "mechanism": node.get("mechanism", node.get("scheme_id")),
            "axes": node.get("factors", {}),
        }
        prediction = predict(model, row)
        utility = (
            prediction["speedup"]
            + beta * prediction["sigma"]
            - weights["cost"] * float(node.get("cost", 0.0))
            - weights["risk"] * float(node.get("risk", 0.0))
        )
        ranked.append(
            {
                "scheme_id": node.get("scheme_id"),
                "utility": utility,
                "prediction": prediction,
            }
        )
    return sorted(ranked, key=lambda item: -item["utility"])
