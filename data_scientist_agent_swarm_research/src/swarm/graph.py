# src/swarm/graph.py

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.redis import RedisSaver
from src.swarm.state import SwarmState, SwarmPhase
from src.shared.config import SharedConfig

cfg = SharedConfig()


def _checkpointer():
    """DragonflyDB (Redis-compatible). Falls back to None if unavailable."""
    url = cfg.DRAGONFLY_URL
    if not url:
        return None
    try:
        saver = RedisSaver(redis_url=url)
        return saver
    except Exception:
        return None


def build_swarm_graph() -> StateGraph:
    graph = StateGraph(SwarmState)

    graph.add_node("crawl_research", crawl_research_node)
    graph.add_node("load_context", load_context_node)
    graph.add_node("plan", strategist_node)
    graph.add_node("design", engineer_node)
    graph.add_node("execute", execution_node)
    graph.add_node("evaluate", evaluation_node)
    graph.add_node("learn", meta_learner_node)
    graph.add_node("circuit_break", circuit_break_node)

    graph.set_entry_point("crawl_research")
    graph.add_edge("crawl_research", "load_context")
    graph.add_edge("load_context", "plan")
    graph.add_edge("plan", "design")
    graph.add_edge("design", "execute")
    graph.add_edge("execute", "evaluate")
    graph.add_edge("evaluate", "learn")

    graph.add_conditional_edges(
        "learn",
        should_continue,
        {"continue": "crawl_research", "break": "circuit_break"},
    )
    graph.add_edge("circuit_break", END)

    return graph.compile(checkpointer=_checkpointer())


def should_continue(state: SwarmState) -> str:
    if state.consecutive_no_improvement >= cfg.CIRCUIT_BREAKER_THRESHOLD:
        return "break"
    return "continue"


def crawl_research_node(state: SwarmState) -> dict:
    """Crawl 20 new research items via arXiv API + Tavily. Runs in orchestrator pod."""
    from src.swarm.research.crawler import run_crawl_cycle
    summary = run_crawl_cycle()
    return {"crawl_summary": summary}


def load_context_node(state: SwarmState) -> dict:
    """Load fresh context at the start of each cycle."""
    from src.shared.ch_client import get_client
    ch = get_client()

    rows = ch.query(
        "SELECT pair, timeframe FROM fxs_serving_universe WHERE active = 1"
    ).named_results()
    available = [dict(r) for r in rows]

    insights = ch.query(
        "SELECT text FROM fxs_insights WHERE status = 'active' "
        "ORDER BY confidence DESC LIMIT 50"
    ).named_results()

    from src.shared.mlflow_utils import get_all_champion_metrics
    champions = get_all_champion_metrics(available)

    from src.swarm.memory.research_store import query_research_for_cycle
    research = query_research_for_cycle(
        allocation=state.allocation,
        champion_metrics=champions,
        past_experiment_strategies=[
            e.get("strategy_type") for e in state.experiment_results[-20:]
        ],
        limit_per_direction=5,
    )

    return {
        "available_pairs": available,
        "active_insights": [r["text"] for r in insights],
        "champion_metrics": champions,
        "relevant_research": research,
        "cycle_number": state.cycle_number + 1,
    }


def strategist_node(state: SwarmState) -> dict:
    from src.swarm.agents.strategist import run_strategist
    return run_strategist(state)


def engineer_node(state: SwarmState) -> dict:
    from src.swarm.agents.engineer import run_engineer
    return run_engineer(state)


def execution_node(state: SwarmState) -> dict:
    """Build + submit Argo Workflow via Hera, poll for completion."""
    from src.swarm.hera_submit import submit_swarm_cycle, poll_workflow
    import uuid

    cycle_id = f"{state.cycle_number}-{uuid.uuid4().hex[:6]}"
    wf_name = submit_swarm_cycle(
        cycle_id=cycle_id,
        experiments=state.experiment_specs,
        generated_code=state.generated_code,
    )
    result = poll_workflow(wf_name)

    experiment_results = []
    for spec in state.experiment_specs:
        exp_id = spec["experiment_id"]
        eval_node_name = f"eval-{exp_id[:8]}".lower()
        node_data = result.get("nodes", {})
        experiment_results.append({"experiment_id": exp_id, "status": "pending_parse"})

    return {"experiment_results": experiment_results}


def evaluation_node(state: SwarmState) -> dict:
    """DETERMINISTIC — no LLM."""
    from src.swarm.evaluator import run_evaluation
    return run_evaluation(state)


def meta_learner_node(state: SwarmState) -> dict:
    from src.swarm.agents.meta_learner import run_meta_learner
    return run_meta_learner(state)


def circuit_break_node(state: SwarmState) -> dict:
    from src.shared.discord import notify_discord
    notify_discord(
        f"CIRCUIT BREAKER: {state.consecutive_no_improvement} consecutive "
        f"experiments without improvement. Cycle {state.cycle_number}."
    )
    return {"phase": SwarmPhase.CIRCUIT_BREAK}


if __name__ == "__main__":
    app = build_swarm_graph()
    initial_state = SwarmState()
    config = {"configurable": {"thread_id": "fx-swarm-main"}}
    for event in app.stream(initial_state, config=config):
        print(f"Event: {list(event.keys())}")
