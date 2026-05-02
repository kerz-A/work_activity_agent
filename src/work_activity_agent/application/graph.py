"""Сборка LangGraph пайплайна.

Collector -> ImageRedaction -> Vision -> Classifier -> Relevance ->
  Timeline -> Scoring -> Reports -> END
"""

from __future__ import annotations

from typing import Any

from work_activity_agent.application.nodes.classifier import make_classifier_node
from work_activity_agent.application.nodes.collector import make_collector_node
from work_activity_agent.application.nodes.image_redaction import make_image_redaction_node
from work_activity_agent.application.nodes.ocr_signals import make_ocr_signals_node
from work_activity_agent.application.nodes.relevance import make_relevance_node
from work_activity_agent.application.nodes.reports import make_reports_node
from work_activity_agent.application.nodes.scoring import make_scoring_node
from work_activity_agent.application.nodes.timeline import make_timeline_node
from work_activity_agent.application.nodes.vision import make_vision_node
from work_activity_agent.application.state import AgentState
from work_activity_agent.config.container import Deps


def build_graph(deps: Deps) -> Any:
    """Собрать и скомпилировать LangGraph пайплайн.

    :param deps: контейнер зависимостей
    :return: CompiledGraph LangGraph

    Checkpointing намеренно не включаем в MVP — SqliteSaver требует context manager,
    усложняет lifecycle. Включается отдельной обвязкой при необходимости resume.
    """
    from langgraph.graph import END, StateGraph

    graph: Any = StateGraph(AgentState)

    graph.add_node("collector", make_collector_node(deps))
    graph.add_node("image_redaction", make_image_redaction_node(deps))
    graph.add_node("ocr_signals", make_ocr_signals_node(deps))
    graph.add_node("vision", make_vision_node(deps))
    graph.add_node("classifier", make_classifier_node(deps))
    graph.add_node("relevance", make_relevance_node(deps))
    graph.add_node("timeline", make_timeline_node(deps))
    graph.add_node("scoring", make_scoring_node(deps))
    graph.add_node("reports", make_reports_node(deps))

    graph.set_entry_point("collector")
    graph.add_edge("collector", "image_redaction")
    graph.add_edge("image_redaction", "ocr_signals")
    graph.add_edge("ocr_signals", "vision")
    graph.add_edge("vision", "classifier")
    graph.add_edge("classifier", "relevance")
    graph.add_edge("relevance", "timeline")
    graph.add_edge("timeline", "scoring")
    graph.add_edge("scoring", "reports")
    graph.add_edge("reports", END)

    return graph.compile()
