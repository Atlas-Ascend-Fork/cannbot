#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""gene_ops.py 单元测试（python3 -m unittest test_gene_ops -v）。

覆盖：选择概率和 / 精英必选 / 变异率边界 / G1 指纹去重 / G2 硬排除 / G6 归一化公式。
纯标准库，可在无 NPU 环境运行。
"""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import gene_ops  # noqa: E402


def make_pool() -> dict:
    return {
        "generation": 1,
        "best_speedup": 1.0,
        "genes": [
            {"gene_id": "G001", "source": "kb_guides", "status": "active",
             "fitness": 1.8, "params": {"block": 128}, "conflicts_with": []},
            {"gene_id": "G002", "source": "kb_guides", "status": "active",
             "fitness": 1.2, "params": {}, "conflicts_with": []},
            {"gene_id": "G003", "source": "kb_runbooks", "status": "active",
             "fitness": 0.6, "params": {"stages": 3}, "conflicts_with": ["G004"]},
            {"gene_id": "G004", "source": "kb_runbooks", "status": "active",
             "fitness": 0.4, "params": {}, "conflicts_with": ["G003"]},
            {"gene_id": "G005", "source": "kb_runbooks", "status": "candidate",
             "fitness": None, "params": {}, "conflicts_with": []},
        ],
        "tested_combos": {},
        "banned_genes": [],
        "card_offsets": {},
    }


class TestSelect(unittest.TestCase):
    def test_weights_sum_positive(self):
        """适应度比例选择的权重和等于 Σfitness（null 记 1）。"""
        pool = make_pool()
        candidates = gene_ops.eligible_genes(pool)
        weights = [gene_ops.weight_of(g) for g in candidates]
        self.assertAlmostEqual(sum(weights), 1.8 + 1.2 + 0.6 + 0.4)

    def test_null_fitness_equal_weight(self):
        """全 null 适应度池 -> 等权重随机选择（round.md Step G1 约束）。"""
        pool = make_pool()
        for g in pool["genes"]:
            g["fitness"] = None
        candidates = gene_ops.eligible_genes(pool)
        weights = {gene_ops.weight_of(g) for g in candidates}
        self.assertEqual(weights, {1.0})

    def test_elite_retained_banned_filtered(self):
        """精英组合直接存活，但 banned 基因被硬过滤。"""
        pool = make_pool()
        pool["banned_genes"].append({"gene_id": "G002", "reason": "test", "round": 1})
        elite = gene_ops.elite_combo(pool, ["G001", "G002"])
        self.assertEqual(elite, ["G001"])

    def test_respects_conflicts(self):
        """互斥基因不得共存。"""
        pool = make_pool()
        self.assertFalse(gene_ops.conflicts_ok(pool, ["G003", "G004"]))
        self.assertTrue(gene_ops.conflicts_ok(pool, ["G001", "G003"]))

    def test_select_combo_size_and_dedup(self):
        pool = make_pool()
        rng = random.Random(42)
        for i in range(50):
            combo = gene_ops.select_combo(pool, random.Random(i))
            self.assertGreaterEqual(len(combo), 2)
            self.assertLessEqual(len(combo), 5)
            self.assertEqual(len(combo), len(set(combo)))
            self.assertTrue(gene_ops.conflicts_ok(pool, combo))

    def test_candidate_excluded_by_default(self):
        pool = make_pool()
        rng = random.Random(7)
        for i in range(30):
            combo = gene_ops.select_combo(pool, random.Random(i))
            self.assertNotIn("G005", combo)


class TestMutate(unittest.TestCase):
    def test_zero_rate_no_mutation(self):
        pool = make_pool()
        result = gene_ops.mutate(pool, ["G001", "G003"], rate=0.0, rng=random.Random(1))
        self.assertEqual(result["genes"], ["G001", "G003"])
        self.assertEqual(result["mutations"], [])

    def test_full_rate_always_mutates(self):
        """rate=1.0 时每个基因必产生变异动作（param/drop/replace 之一）。"""
        pool = make_pool()
        for i in range(20):
            pool = make_pool()
            result = gene_ops.mutate(pool, ["G003"], rate=1.0, rng=random.Random(i))
            self.assertEqual(len(result["mutations"]), 1)

    def test_kb_guides_rate_halved(self):
        """kb_guides 来源基因变异率减半：rate=0.3 时有效 0.15。"""
        pool = make_pool()
        mutated = sum(
            1
            for i in range(4000)
            if gene_ops.mutate(make_pool(), ["G001"], rate=0.3, rng=random.Random(i))["mutations"]
        )
        # 0.15 ± 3σ（σ≈0.0057）
        self.assertLess(abs(mutated / 4000 - 0.15), 0.03)


class TestComboFingerprint(unittest.TestCase):
    def test_hash_order_insensitive(self):
        """G1：组合指纹对基因顺序不敏感。"""
        self.assertEqual(gene_ops.combo_hash(["G002", "G001"]), gene_ops.combo_hash(["G001", "G002"]))

    def test_tested_combo_roundtrip(self):
        pool = make_pool()
        self.assertIsNone(gene_ops.lookup_tested_combo(pool, ["G001", "G002"]))
        gene_ops.record_tested_combo(pool, ["G001", "G002"], fitness=0.81, round_index=2)
        hit = gene_ops.lookup_tested_combo(pool, ["G002", "G001"])
        self.assertEqual(hit["fitness"], 0.81)
        self.assertEqual(hit["round"], 2)


class TestBannedGene(unittest.TestCase):
    def test_banned_excluded_from_output(self):
        """G2：banned 基因在交叉/精英输出中被硬排除。"""
        pool = make_pool()
        pool["banned_genes"].append({"gene_id": "G003", "reason": "NZ 方向失败", "round": 2})
        rng = random.Random(3)
        result = gene_ops.crossover(pool, ["G001", "G003"], ["G002", "G003", "G004"], rate=1.0, rng=rng)
        self.assertNotIn("G003", result["child"])
        self.assertTrue(gene_ops.conflicts_ok(pool, result["child"]))


class TestUpdateFitness(unittest.TestCase):
    def test_smoothing_formula(self):
        """new = 0.3*old + 0.7*speedup（无卡偏移）。"""
        pool = make_pool()
        gene_ops.update_fitness(
            pool,
            [{"route_id": "route-1", "gene_ids": ["G001"], "speedup": 1.0, "status": "success", "card_id": None}],
            round_index=2,
        )
        self.assertAlmostEqual(gene_ops.gene_by_id(pool, "G001")["fitness"], 0.3 * 1.8 + 0.7 * 1.0)

    def test_card_offset_normalization(self):
        """G6：speedup / (1 + offset_pct/100)。"""
        pool = make_pool()
        pool["card_offsets"] = {"card-9": 10.0}  # 慢 10% 的卡
        gene_by = gene_ops.gene_by_id(pool, "G002")
        gene_by["fitness"] = None  # 旧值为 null -> 直接取归一化实测值
        gene_ops.update_fitness(
            pool,
            [{"route_id": "route-1", "gene_ids": ["G002"], "speedup": 1.1, "status": "success", "card_id": "card-9"}],
            round_index=2,
        )
        self.assertAlmostEqual(gene_by["fitness"], 1.1 / 1.1)

    def test_failed_route_skipped(self):
        pool = make_pool()
        gene_ops.update_fitness(
            pool,
            [{"route_id": "route-x", "gene_ids": ["G001"], "speedup": 0.1, "status": "failed"}],
            round_index=2,
        )
        self.assertEqual(gene_ops.gene_by_id(pool, "G001")["fitness"], 1.8)

    def test_rejected_route_bans_genes(self):
        """G2：verdict rejected 的基因自动入 banned_genes。"""
        pool = make_pool()
        gene_ops.update_fitness(
            pool,
            [{
                "route_id": "route-y", "gene_ids": ["G004"], "speedup": 0.2,
                "status": "rejected", "reject_reason": "NZ 越界",
            }],
            round_index=3,
        )
        self.assertIn("G004", gene_ops.banned_ids(pool))
        # banned 基因后续选择不可见
        self.assertNotIn("G004", [g["gene_id"] for g in gene_ops.eligible_genes(pool)])

    def test_success_route_recorded_in_tested_combos(self):
        """G1：成功 route 记入已测组合。"""
        pool = make_pool()
        gene_ops.update_fitness(
            pool,
            [{"route_id": "route-1", "gene_ids": ["G001", "G002"], "speedup": 0.9, "status": "success"}],
            round_index=4,
        )
        hit = gene_ops.lookup_tested_combo(pool, ["G002", "G001"])
        self.assertIsNotNone(hit)
        self.assertEqual(hit["round"], 4)


if __name__ == "__main__":
    unittest.main()
