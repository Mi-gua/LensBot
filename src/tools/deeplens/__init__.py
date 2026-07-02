from tools.deeplens.analysis import DeepLensAnalysisTool
from tools.deeplens.curriculum import DeepLensCurriculumTool
from tools.deeplens.finetune import DeepLensFinetuneTool
from tools.deeplens.strategy import DeepLensAdjustStrategyTool, DeepLensInspectCheckpointTool
from tools.deeplens.structure import DeepLensAdjustStructureTool


DEEPLENS_TOOLS = [
    DeepLensAdjustStructureTool(),
    DeepLensCurriculumTool(),
    DeepLensFinetuneTool(),
    DeepLensInspectCheckpointTool(),
    DeepLensAdjustStrategyTool(),
    DeepLensAnalysisTool(),
]


__all__ = [
    "DEEPLENS_TOOLS",
    "DeepLensAnalysisTool",
    "DeepLensAdjustStrategyTool",
    "DeepLensAdjustStructureTool",
    "DeepLensCurriculumTool",
    "DeepLensFinetuneTool",
    "DeepLensInspectCheckpointTool",
]
