"""Graph assembly for matchup gameplan synthesis."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from pokecoach_python.graphs.matchup_gameplan.nodes.generate_gameplan_node import (
    build_generate_gameplan_node,
)
from pokecoach_python.graphs.matchup_gameplan.nodes.load_sources_node import (
    build_load_sources_node,
)
from pokecoach_python.graphs.matchup_gameplan.states import MatchupGameplanState


def create_matchup_gameplan_graph(store, client):
    workflow = StateGraph(MatchupGameplanState)
    workflow.add_node("load_sources", build_load_sources_node(store))
    workflow.add_node("generate_gameplan", build_generate_gameplan_node(client))
    workflow.add_edge(START, "load_sources")
    workflow.add_edge("load_sources", "generate_gameplan")
    workflow.add_edge("generate_gameplan", END)
    return workflow.compile()
