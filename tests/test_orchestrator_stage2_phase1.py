"""Stage-2 integration test: orchestrator wires ProductAdvice + OpsAdvice."""
from __future__ import annotations

import os
import unittest

from app.schemas.final_response import AnalyzeResponse


class OrchestratorStage2Tests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["MODEL_MODE"] = "mock"
        from app.services.orchestrator import AnalysisOrchestrator
        self.orch = AnalysisOrchestrator()

    def test_stage2_outputs_present(self):
        resp: AnalyzeResponse = self.orch.analyze(["user_001"])
        self.assertEqual(len(resp.results), 1)
        result = resp.results[0]
        self.assertIsNotNone(result.product_advice)
        self.assertIsNotNone(result.ops_advice)
        for out in (result.product_advice, result.ops_advice):
            self.assertIn("structured_result", out.model_dump())
            self.assertIn(out.structured_result.get("status"), {"ok", "data_missing"})


if __name__ == "__main__":
    unittest.main()
