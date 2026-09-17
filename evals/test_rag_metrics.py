from evals.rag_metrics import ranking_metrics


def test_ranking_metrics_uses_graded_relevance_and_reports_coverage():
    metrics = ranking_metrics(["low", "best", "unjudged", "bad"], {"low": 1, "best": 3, "bad": 0}, 4)
    assert metrics["recall_at_k"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["ndcg_at_k"] < 1.0  # The most important evidence was not ranked first.
    assert metrics["judged_at_k"] == 3
    assert metrics["unjudged_at_k"] == 1
