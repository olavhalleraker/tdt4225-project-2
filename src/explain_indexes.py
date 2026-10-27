"""
Index use of some of the queries, shown with explain().

Shows which queries use an index (IXSCAN / TEXT_MATCH) and which have to scan
the whole collection (COLLSCAN), and how much space the indexes take. Used in
the report to justify the choice of indexes.

Run:  python explain_indexes.py | tee ../output/explain_indexes.txt
"""
from tabulate import tabulate

from DbConnector import DbConnector


def plan_stages(node):
    """All 'stage' names in an explain document, from the top of the plan down."""
    stages = []
    if isinstance(node, dict):
        if isinstance(node.get("stage"), str):
            stages.append(node["stage"] + (" (%s)" % node["indexName"] if "indexName" in node else ""))
        for key, value in node.items():
            if key not in ("rejectedPlans", "allPlansExecution"):
                stages += plan_stages(value)
    elif isinstance(node, list):
        for value in node:
            stages += plan_stages(value)
    return stages


def find_stats(explain):
    """(documents examined, index keys examined, documents returned) from executionStats."""
    stats = explain.get("executionStats", {})
    return stats.get("totalDocsExamined"), stats.get("totalKeysExamined"), stats.get("nReturned")


class IndexExplainer:

    def __init__(self):
        self.connection = DbConnector()
        self.db = self.connection.db

    def explain_finds(self):
        queries = [
            ("Task 7: text search for 'noir'", "movies", {"$text": {"$search": "noir"}}),
            ("Ratings of one user (left prefix of the unique index)", "ratings", {"user_id": 1}),
            ("Ratings of one movie (no index on movie_id)", "ratings", {"movie_id": 862}),
        ]
        rows = []
        for title, collection, query in queries:
            explain = self.db[collection].find(query).explain()
            docs, keys, returned = find_stats(explain)
            rows.append([title, collection, " <- ".join(dict.fromkeys(plan_stages(explain["queryPlanner"]))),
                         docs, keys, returned])
        print(tabulate(rows, headers=["Query", "Collection", "Plan (winning)", "Docs examined", "Keys examined",
                                      "Returned"], tablefmt="simple", intfmt=","))

    def explain_aggregation(self):
        # The $group per user in task 10. queryPlanner only, so the 26 million
        # ratings are not actually aggregated.
        explain = self.db.command("explain", {"aggregate": "ratings",
                                              "pipeline": [{"$group": {"_id": "$user_id", "ratings": {"$sum": 1}}}],
                                              "cursor": {}}, verbosity="queryPlanner")
        print("\nTask 10, $group per user on ratings: " + " <- ".join(dict.fromkeys(plan_stages(explain))))

    def index_sizes(self):
        rows = []
        for name in ("movies", "ratings"):
            stats = self.db.command("collStats", name)
            for index, size in stats["indexSizes"].items():
                rows.append([name, index, "%.1f" % (size / 1e6)])
            rows.append([name, "(data, storage)", "%.1f, %.1f" % (stats["size"] / 1e6, stats["storageSize"] / 1e6)])
        print("\nSizes in MB:")
        print(tabulate(rows, headers=["Collection", "Index", "MB"], tablefmt="simple"))


def main():
    program = None
    try:
        program = IndexExplainer()
        program.explain_finds()
        program.explain_aggregation()
        program.index_sizes()
    except Exception as e:
        print("ERROR: Failed to use database:", e)
        raise
    finally:
        if program:
            program.connection.close_connection()


if __name__ == "__main__":
    main()
