"""Algebra tests run when PyTorch is available; no model download required."""

import importlib.util
import unittest

HAS_TORCH = importlib.util.find_spec("torch") is not None


@unittest.skipUnless(HAS_TORCH, "PyTorch not installed in lightweight test runner")
class WeightSpaceTests(unittest.TestCase):
    def setUp(self):
        import torch

        self.torch = torch
        from tinycoder.weight_space import cap_factors, nullspace_factors, rank_one_factors

        self.cap = cap_factors
        self.nullspace = nullspace_factors
        self.rank_one = rank_one_factors

    def test_rank_one_solves_single_key_mapping(self):
        torch = self.torch
        weight = torch.eye(2)
        key = torch.tensor([1.0, 2.0])
        desired = torch.tensor([3.0, 4.0])
        left, right = self.rank_one(weight, key, desired, torch.ones(2), alpha=1.0)
        updated = weight + torch.outer(left, right)
        self.assertTrue(torch.allclose(updated @ key, desired, atol=1e-5))

    def test_nullspace_dampens_only_chosen_direction(self):
        torch = self.torch
        weight = torch.eye(2)
        key = torch.tensor([1.0, 0.0])
        left, right = self.nullspace(weight, key, strength=1.0)
        updated = weight + torch.outer(left, right)
        self.assertTrue(torch.allclose(updated @ key, torch.zeros(2)))
        self.assertTrue(torch.allclose(updated @ torch.tensor([0.0, 1.0]), torch.tensor([0.0, 1.0])))

    def test_safety_cap_limits_frobenius_change(self):
        torch = self.torch
        weight = torch.eye(2)
        left, right, _, scale = self.cap(weight, torch.tensor([100.0, 0.0]),
                                         torch.tensor([1.0, 0.0]), max_relative_change=0.01)
        norm = torch.linalg.vector_norm(torch.outer(left, right))
        self.assertLessEqual(norm.item(), 0.01 * torch.linalg.vector_norm(weight).item() + 1e-6)
        self.assertLess(scale, 1.0)

    def test_woodbury_inverse_agrees_with_dense_solution(self):
        torch = self.torch
        from tinycoder.rome20 import ridge_inverse_times_key

        keys = [torch.tensor([1.0, 2.0, 0.0, 1.0]),
                torch.tensor([0.0, 1.0, 1.0, 2.0]),
                torch.tensor([1.0, 0.0, 2.0, 0.0])]
        query = torch.tensor([0.5, 1.5, 0.2, -0.3])
        inverse_times, ridge = ridge_inverse_times_key(keys, query)
        k = torch.stack(keys, dim=1).double()
        covariance = ridge * torch.eye(4, dtype=torch.float64) + k @ k.T / len(keys)
        direct = torch.linalg.solve(covariance, query.double())
        self.assertTrue(torch.allclose(inverse_times.double(), direct, rtol=1e-3, atol=1e-4))


if __name__ == "__main__":
    unittest.main()

