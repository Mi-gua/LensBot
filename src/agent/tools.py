from __future__ import annotations

from schema import LensDesignParams
from tools import DesignTool, EvaluationTool, PatentTool, RequirementTool


class AgentTools:
    def __init__(self, default_params: LensDesignParams):
        self.requirements = RequirementTool(default_params)
        self.patents = PatentTool()
        self.design = DesignTool()
        self.evaluation = EvaluationTool()
