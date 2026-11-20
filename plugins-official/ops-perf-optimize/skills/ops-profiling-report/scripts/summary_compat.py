# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Project reviewed producer extensions into an unchanged inspector's schema.

The original summary remains authoritative. Hints/extra FLOPS metadata are
preserved as opaque diagnostics, never promoted to timing or hardware peaks.
"""

from __future__ import annotations

import json
import math
from pathlib import Path


FLOPS_METADATA = {
    "aic_flops_theoretical",
    "aiv_flops_theoretical",
    "aic_flops",
    "aiv_flops",
}


def known_view(records, skill):
    assets = Path(skill) / "assets"
    catalog = json.loads((assets / "summary-catalog.json").read_text())["record_types"]
    metrics = json.loads((assets / "metric-catalog.json").read_text())["sections"]
    projected, hints, extras, unavailable = [], [], {}, []
    for record in records:
        category = record["category"]
        if category == "PerformanceHints" and category not in catalog:
            if (
                set(record) != {"category", "hints"}
                or not isinstance(record["hints"], list)
                or not all(isinstance(item, str) for item in record["hints"])
            ):
                raise ValueError("unreviewed PerformanceHints schema")
            hints.append(record)
            continue
        if category not in catalog:
            raise ValueError(f"unreviewed summary category: {category}")
        definition = catalog[category]
        if category == "OpInfoSummary":
            fields = {item["name"]: item for item in definition["fields"]}
            nullable = {
                name for name, item in fields.items() if "null" in item["json_types"]
            }
        else:
            source = definition["metric_fields"]
            if source["catalog"] != "metric-catalog.json":
                raise ValueError("unknown external metric catalog")
            fields = {
                item["name"]: item
                for item in metrics[source["section"]]["fields"]
                if item["name"] not in source["excluded_fields"]
            }
            fields["category"] = {}
            nullable = set(fields) - {"category"}
        view = {}
        for name, value in record.items():
            if (
                category == "OpInfoSummary"
                and name in FLOPS_METADATA
                and name not in fields
            ):
                if value not in (None, "NA") and (
                    type(value) not in (int, float) or not math.isfinite(value)
                ):
                    raise ValueError(f"invalid opaque FLOPS metadata: {name}")
                extras[name] = value
                continue
            if value == "NA" and name in nullable:
                value = None
                unavailable.append({"category": category, "field": name})
            # Retain unknown fields/order so the external inspector still rejects
            # unrelated schema errors rather than silently accepting them.
            view[name] = value
        projected.append(view)
    if not (hints or extras or unavailable):
        raise ValueError("no reviewed schema compatibility change applies")
    return projected, {
        "id": "npu_compute_summary_extensions_v1",
        "advisory_performance_hints": hints,
        "opaque_op_metadata": extras,
        "unavailable_normalizations": unavailable,
        "scope": (
            "External inspector validates the derived known-field view; "
            "raw extensions retained, not interpreted as proof or peaks."
        ),
    }
