"""Built-in capability class paths."""

BUILTIN_CAPABILITY_CLASSES: dict[str, str] = {
    "chat": "deeptutor.capabilities.chat:ChatCapability",
    "deep_solve": "deeptutor.capabilities.deep_solve:DeepSolveCapability",
    "deep_question": "deeptutor.capabilities.deep_question:DeepQuestionCapability",
    "deep_research": "deeptutor.capabilities.deep_research:DeepResearchCapability",
    "math_animator": "deeptutor.capabilities.math_animator:MathAnimatorCapability",
    "visualize": "deeptutor.capabilities.visualize:VisualizeCapability",
    "content_analyzer": "deeptutor.capabilities.content_analyzer:ContentAnalyzerCapability",
    "socratic_dialog": "deeptutor.capabilities.socratic_dialog:SocraticDialogCapability",
    "learning_guide": "deeptutor.capabilities.learning_guide:LearningGuideCapability",
}
