"""
Part 2 - Answer the ten questions with MongoDB aggregation pipelines and Python.

Run:  python part2_queries.py | tee ../output/part2_results.txt
"""
import csv
import os
import textwrap
import time
from pprint import pprint

from pymongo import DESCENDING
from tabulate import tabulate

from DbConnector import DbConnector

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def print_table(rows, headers, floatfmt=".2f"):
    """Print rows with tabulate: counts get thousands separators, decimals two
    digits (unless floatfmt says otherwise), and ID and year columns are printed
    as they are."""
    # pymongo returns 64-bit integers as bson.int64.Int64, which tabulate does not
    # recognise as integers
    rows = [[int(v) if isinstance(v, int) and not isinstance(v, bool) else v for v in row] for row in rows]
    id_columns = [i for i, h in enumerate(headers) if h.endswith("_id") or h == "year"]
    print(tabulate(rows, headers=headers, tablefmt="simple", floatfmt=floatfmt, intfmt=",",
                   disable_numparse=id_columns or False))


def print_first_document(documents):
    """The first result document as MongoDB returns it (pretty-printed with pprint)."""
    print("First result document:")
    pprint(documents[0], sort_dicts=False)
    print()


def save_csv(filename, headers, rows):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print("(all {:,} rows written to output/{})".format(len(rows), filename))


def date(value):
    return value.strftime("%Y-%m-%d") if value else None


# ---------------------------------------------------------------------- #
# Expressions used in several pipelines

def median(array):
    """Exact median of the non-null numbers in an array expression.

    MongoDB 7.0 has a $median accumulator, but only with method 'approximate'.
    Here the values are sorted, and the median is the mean of the two middle
    values (for an odd count both are the same value). Empty array -> null."""
    values = {"$sortArray": {"input": {"$filter": {"input": array, "cond": {"$ne": ["$$this", None]}}},
                             "sortBy": 1}}
    return {"$let": {
        "vars": {"v": values},
        "in": {"$avg": [
            {"$arrayElemAt": ["$$v", {"$floor": {"$divide": [{"$subtract": [{"$size": "$$v"}, 1]}, 2]}}]},
            {"$arrayElemAt": ["$$v", {"$floor": {"$divide": [{"$size": "$$v"}, 2]}}]},
        ]},
    }}


def decade(date_field):
    """Decade of a date as a number, e.g. 1994-05-01 -> 1990."""
    year = {"$year": date_field}
    return {"$subtract": [year, {"$mod": [year, 10]}]}


def count_if(condition):
    return {"$sum": {"$cond": [condition, 1, 0]}}


def directors_of_movie():
    """Distinct {id, name} of the crew members with job Director."""
    directors = {"$filter": {"input": "$crew", "cond": {"$eq": ["$$this.job", "Director"]}}}
    return {"$setUnion": [{"$map": {"input": directors, "in": {"id": "$$this.id", "name": "$$this.name"}}}]}


def actors_of_movie():
    """Distinct {id, name} of the cast (an actor with two roles counts once)."""
    return {"$setUnion": [{"$map": {"input": "$cast", "in": {"id": "$$this.id", "name": "$$this.name"}}}]}


class MovieQueries:

    def __init__(self):
        self.connection = DbConnector()
        self.client = self.connection.client
        self.db = self.connection.db

    def aggregate(self, collection, pipeline):
        return list(self.db[collection].aggregate(pipeline, allowDiskUse=True))

    # ------------------------------------------------------------------ #
    def task1(self):
        """Directors with >= 5 movies with known revenue: the 10 with the highest
        median revenue, with their movie count and mean vote_average."""
        per_director = [
            {"$unwind": "$crew"},
            {"$match": {"crew.job": "Director"}},
            # A director listed twice for the same movie counts once
            {"$group": {"_id": {"director_id": "$crew.id", "movie_id": "$_id"},
                        "director": {"$first": "$crew.name"},
                        "revenue": {"$first": "$revenue"},
                        "vote_average": {"$first": "$vote_average"}}},
            {"$group": {"_id": "$_id.director_id",
                        "director": {"$first": "$director"},
                        "movies": {"$sum": 1},
                        "movies_with_revenue": count_if({"$ne": ["$revenue", None]}),
                        "revenues": {"$push": "$revenue"},
                        "mean_vote_average": {"$avg": "$vote_average"}}},
        ]
        def top_10(min_movies, min_with_revenue):
            return self.aggregate("movies", per_director + [
                {"$match": {"movies": {"$gte": min_movies}, "movies_with_revenue": {"$gte": min_with_revenue}}},
                {"$project": {"director": 1, "movies": 1, "movies_with_revenue": 1,
                              "median_revenue": median("$revenues"), "mean_vote_average": 1}},
                {"$sort": {"median_revenue": DESCENDING, "movies": DESCENDING, "director": 1}},
                {"$limit": 10},
            ])

        def show(rows):
            print_table([[rank, r["_id"], r["director"], r["movies"], r["movies_with_revenue"],
                          round(r["median_revenue"]), r["mean_vote_average"]] for rank, r in enumerate(rows, start=1)],
                        ["rank", "director_id", "director", "movies", "movies_with_revenue", "median_revenue",
                         "mean_vote_average"])

        # Main answer: >= 5 movies with known revenue, so that every median is
        # computed from at least 5 values (revenue is unknown for most movies)
        rows = top_10(5, 5)
        print("Interpretation: directors with >= 5 movies WITH KNOWN REVENUE (the median is taken over")
        print("the known revenues; movie count and mean vote_average are over all their movies).\n")
        print_first_document(rows)
        show(rows)
        # Literal reading of the question: >= 5 directed movies, median over the
        # known revenues (at least one)
        literal = top_10(5, 1)
        print("\nLiteral reading: directors with >= 5 movies (median over their known revenues, >= 1):")
        show(literal)
        counts = self.aggregate("movies", per_director + [
            {"$group": {"_id": None, "at_least_5_movies": count_if({"$gte": ["$movies", 5]}),
                        "at_least_5_with_revenue": count_if({"$gte": ["$movies_with_revenue", 5]})}}])[0]
        print("\nDirectors with >= 5 movies: {:,}, of these with >= 5 known revenues: {:,}"
              .format(counts["at_least_5_movies"], counts["at_least_5_with_revenue"]))

    def task2(self):
        """Actor pairs that have co-starred in >= 3 movies, with the number of
        co-appearances and the average vote_average of these movies."""
        rows = self.aggregate("movies", [
            {"$match": {"cast.1": {"$exists": True}}},  # at least two cast entries
            {"$project": {"vote_average": 1, "actor": actors_of_movie()}},
            # Pair every actor with every other actor of the same movie, each pair once
            {"$addFields": {"other": "$actor"}},
            {"$unwind": "$actor"},
            {"$unwind": "$other"},
            {"$match": {"$expr": {"$lt": ["$actor.id", "$other.id"]}}},
            {"$group": {"_id": {"actor_1_id": "$actor.id", "actor_2_id": "$other.id"},
                        "actor_1": {"$first": "$actor.name"},
                        "actor_2": {"$first": "$other.name"},
                        "co_appearances": {"$sum": 1},
                        "avg_vote_average": {"$avg": "$vote_average"}}},
            {"$match": {"co_appearances": {"$gte": 3}}},
            {"$sort": {"co_appearances": DESCENDING, "avg_vote_average": DESCENDING, "actor_1": 1, "actor_2": 1}},
        ])
        headers = ["actor_1_id", "actor_1", "actor_2_id", "actor_2", "co_appearances", "avg_vote_average"]
        table = [[r["_id"]["actor_1_id"], r["actor_1"], r["_id"]["actor_2_id"], r["actor_2"], r["co_appearances"],
                  r["avg_vote_average"]] for r in rows]
        print("Actor pairs with >= 3 movies together: {:,}\n".format(len(rows)))
        print_first_document(rows)
        print("Top 30 by co-appearances (ties by average vote_average):")
        print_table([[rank] + row for rank, row in enumerate(table[:30], start=1)], ["rank"] + headers)
        save_csv("task2_actor_pairs.csv", headers, table)

    def task3(self):
        """The 10 actors with >= 10 credited movies that have appeared in the most
        distinct genres. As example genres we show the actor's 5 most common genres."""
        n_genres = len(self.db.movies.distinct("genres"))
        rows = self.aggregate("movies", [
            {"$unwind": "$cast"},
            # One entry per actor and movie (an actor with two roles counts once)
            {"$group": {"_id": "$cast.id",
                        "actor": {"$first": "$cast.name"},
                        "movies": {"$addToSet": {"movie_id": "$_id", "genres": "$genres"}}}},
            {"$project": {"actor": 1, "movies": 1,
                          "credited_movies": {"$size": "$movies"},
                          "genres": {"$reduce": {"input": "$movies.genres", "initialValue": [],
                                                 "in": {"$setUnion": ["$$value", "$$this"]}}}}},
            {"$match": {"credited_movies": {"$gte": 10}}},
            {"$project": {"actor": 1, "credited_movies": 1,
                          "distinct_genres": {"$size": "$genres"},
                          # Number of the actor's movies in each of the actor's genres
                          "genre_counts": {"$map": {"input": "$genres", "as": "genre", "in": {
                              "genre": "$$genre",
                              "movies": {"$size": {"$filter": {"input": "$movies",
                                                               "cond": {"$in": ["$$genre", "$$this.genres"]}}}}}}}}},
            {"$project": {"actor": 1, "credited_movies": 1, "distinct_genres": 1,
                          "example_genres": {"$slice": [{"$sortArray": {"input": "$genre_counts",
                                                                        "sortBy": {"movies": -1, "genre": 1}}}, 5]}}},
            {"$sort": {"distinct_genres": DESCENDING, "credited_movies": 1, "actor": 1}},
        ])
        top = rows[:10]
        print("Actors with >= 10 credited movies: {:,}. Of these, {} have all {} genres and {} have {}.\n".format(
            len(rows), sum(1 for r in rows if r["distinct_genres"] == n_genres), n_genres,
            sum(1 for r in rows if r["distinct_genres"] == n_genres - 1), n_genres - 1))
        print_first_document(top)
        print("Top 10 by distinct genres (ties: fewer credited movies first). Example genres = the actor's")
        print("5 most common genres, with the number of the actor's movies in that genre:")
        print_table([[rank, r["_id"], r["actor"], r["credited_movies"], r["distinct_genres"],
                      ", ".join("%s (%d)" % (g["genre"], g["movies"]) for g in r["example_genres"])]
                     for rank, r in enumerate(top, start=1)],
                    ["rank", "actor_id", "actor", "credited_movies", "distinct_genres", "example_genres"])

    def task4(self):
        """Collections with >= 3 movies: the 10 with the largest total revenue, with
        movie count, total revenue, median vote_average and first -> last release."""
        rows = self.aggregate("movies", [
            {"$match": {"belongs_to_collection.name": {"$ne": None}}},
            {"$group": {"_id": "$belongs_to_collection.id",
                        "collection": {"$first": "$belongs_to_collection.name"},
                        "movies": {"$sum": 1},
                        "movies_with_revenue": count_if({"$ne": ["$revenue", None]}),
                        "total_revenue": {"$sum": "$revenue"},
                        "vote_averages": {"$push": "$vote_average"},
                        "earliest_release": {"$min": "$release_date"},
                        "latest_release": {"$max": "$release_date"}}},
            {"$match": {"movies": {"$gte": 3}}},
            {"$project": {"collection": 1, "movies": 1, "movies_with_revenue": 1, "total_revenue": 1,
                          "median_vote_average": median("$vote_averages"),
                          "earliest_release": 1, "latest_release": 1}},
            {"$sort": {"total_revenue": DESCENDING}},
            {"$limit": 10},
        ])
        print_first_document(rows)
        print_table([[rank, r["collection"], r["movies"], r["movies_with_revenue"], r["total_revenue"],
                      r["median_vote_average"], "%s -> %s" % (date(r["earliest_release"]), date(r["latest_release"]))]
                     for rank, r in enumerate(rows, start=1)],
                    ["rank", "collection", "movies", "movies_with_revenue", "total_revenue", "median_vote_average",
                     "earliest -> latest release"])
        print("\ntotal_revenue is the sum of the known revenues only (see movies_with_revenue), so it is a")
        print("lower bound for collections where some revenues are unknown.")

    def task5(self):
        """Median runtime and movie count per decade and primary genre (the first
        element in genres), sorted by decade and then median runtime (desc)."""
        rows = self.aggregate("movies", [
            # Movies with unknown runtime are counted, but the median ignores them
            {"$match": {"release_date": {"$ne": None}, "genres.0": {"$exists": True}}},
            {"$group": {"_id": {"decade": decade("$release_date"), "primary_genre": {"$arrayElemAt": ["$genres", 0]}},
                        "movies": {"$sum": 1},
                        "movies_with_runtime": count_if({"$ne": ["$runtime", None]}),
                        "runtimes": {"$push": "$runtime"}}},
            {"$project": {"_id": 0, "decade": "$_id.decade", "primary_genre": "$_id.primary_genre",
                          "movies": "$movies", "movies_with_runtime": "$movies_with_runtime",
                          "median_runtime": median("$runtimes")}},
            {"$sort": {"decade": 1, "median_runtime": DESCENDING, "movies": DESCENDING, "primary_genre": 1}},
        ])
        headers = ["decade", "primary_genre", "movies", "movies_with_runtime", "median_runtime"]
        table = [["%ds" % r["decade"], r["primary_genre"], r["movies"], r["movies_with_runtime"], r["median_runtime"]]
                 for r in rows]
        print("Movies with release date and at least one genre: {:,} ({:,} with known runtime), in {} (decade, genre)"
              " groups.".format(sum(r["movies"] for r in rows), sum(r["movies_with_runtime"] for r in rows), len(rows)))
        print("Sorted by decade (ascending), then median runtime (descending). Groups with only a few movies")
        print("(e.g. before 1910) give medians that say little.\n")
        print_first_document(rows)
        print_table(table, headers)
        save_csv("task5_runtime_by_decade_and_genre.csv", headers, table)

    def task6(self):
        """Share of women among the top-5 billed cast of each movie, averaged per
        decade (cast members with unknown gender are ignored)."""
        rows = self.aggregate("movies", [
            {"$match": {"release_date": {"$ne": None}, "cast.0": {"$exists": True}}},
            {"$project": {"decade": decade("$release_date"),
                          "top_5": {"$slice": [{"$sortArray": {"input": "$cast", "sortBy": {"order": 1}}}, 5]}}},
            {"$project": {"decade": 1,
                          "known": {"$size": {"$filter": {"input": "$top_5", "cond": {"$ne": ["$$this.gender", None]}}}},
                          "female": {"$size": {"$filter": {"input": "$top_5",
                                                           "cond": {"$eq": ["$$this.gender", "female"]}}}}}},
            {"$match": {"known": {"$gt": 0}}},  # movies where no top-5 gender is known are not used
            {"$group": {"_id": "$decade",
                        "avg_female_proportion": {"$avg": {"$divide": ["$female", "$known"]}},
                        "movies": {"$sum": 1}}},
            {"$sort": {"avg_female_proportion": DESCENDING, "movies": DESCENDING}},
        ])
        print_first_document(rows)
        print_table([["%ds" % r["_id"], r["avg_female_proportion"], r["movies"]] for r in rows],
                    ["decade", "avg_female_proportion", "movies"], floatfmt=".4f")
        print("\nMovies used in total: {:,}".format(sum(r["movies"] for r in rows)))
        print("avg_female_proportion is the mean of the per-movie proportions (female / known gender among")
        print("the top 5). Decades with only a few movies (e.g. the 1870s, 1890s and 2020s) are not reliable.")

    def task7(self):
        """The 20 movies with the highest vote_average (vote_count >= 50) whose
        overview or tagline matches "noir" or "neo-noir" in a text search."""
        # The text index splits "neo-noir" into "neo" and "noir", so every
        # neo-noir match is also a noir match, and searching for "noir" finds both.
        search = {"$text": {"$search": "noir"}}
        text = {"$concat": [{"$ifNull": ["$overview", ""]}, " ", {"$ifNull": ["$tagline", ""]}]}
        rows = self.aggregate("movies", [
            {"$match": {**search, "vote_count": {"$gte": 50}}},
            {"$project": {"_id": 0, "title": 1, "year": {"$year": "$release_date"}, "vote_average": 1,
                          "vote_count": 1,
                          "matched": {"$cond": [{"$regexMatch": {"input": text, "regex": "neo-noir", "options": "i"}},
                                                "neo-noir", "noir"]}}},
            {"$sort": {"vote_average": DESCENDING, "vote_count": DESCENDING}},
            {"$limit": 20},
        ])
        noir_ids = {m["_id"] for m in self.db.movies.find(search, {"_id": 1})}
        print('Text search "noir": {:,} movies, {:,} of them with vote_count >= 50.'.format(
            len(noir_ids), self.db.movies.count_documents({**search, "vote_count": {"$gte": 50}})))
        also_neo = [m["title"] for m in self.db.movies.find({"$text": {"$search": "noir neo-noir"}}, {"title": 1})
                    .sort("vote_count", DESCENDING) if m["_id"] not in noir_ids]
        print('(Searching "noir neo-noir" would add {} movies where only "neo" matches, e.g. {}.)\n'
              .format(len(also_neo), ", ".join(also_neo[:3])))
        print_first_document(rows)
        print_table([[rank, r["title"], r["year"], r["vote_average"], r["vote_count"], r["matched"]]
                     for rank, r in enumerate(rows, start=1)],
                    ["rank", "title", "year", "vote_average", "vote_count", "matched"])

    def task8(self):
        """The 20 director-actor pairs with >= 3 movies together (movies with
        vote_count >= 100) with the highest mean vote_average, with films count
        and mean revenue."""
        rows = self.aggregate("movies", [
            {"$match": {"vote_count": {"$gte": 100}}},
            {"$project": {"vote_average": 1, "revenue": 1, "director": directors_of_movie(),
                          "actor": actors_of_movie()}},
            {"$unwind": "$director"},
            {"$unwind": "$actor"},
            {"$match": {"$expr": {"$ne": ["$director.id", "$actor.id"]}}},  # not a director in their own film
            {"$group": {"_id": {"director_id": "$director.id", "actor_id": "$actor.id"},
                        "director": {"$first": "$director.name"},
                        "actor": {"$first": "$actor.name"},
                        "films": {"$sum": 1},
                        "mean_vote_average": {"$avg": "$vote_average"},
                        "films_with_revenue": count_if({"$ne": ["$revenue", None]}),
                        "mean_revenue": {"$avg": "$revenue"}}},
            {"$match": {"films": {"$gte": 3}}},
            {"$sort": {"mean_vote_average": DESCENDING, "films": DESCENDING, "director": 1, "actor": 1}},
            {"$limit": 20},
        ])
        print_first_document(rows)
        print_table([[rank, r["director"], r["actor"], r["films"], r["mean_vote_average"], r["films_with_revenue"],
                      None if r["mean_revenue"] is None else round(r["mean_revenue"])]
                     for rank, r in enumerate(rows, start=1)],
                    ["rank", "director", "actor", "films", "mean_vote_average", "films_with_revenue", "mean_revenue"])

    def task9(self):
        """Movies with original_language != "en" where a production country (or
        company) is the United States: the 10 most common original languages,
        with count and one example title."""
        us_country = {"production_countries.iso_3166_1": "US"}
        # Companies have no country in the data, only a name
        us_company = {"production_companies.name": {"$regex": "United States"}}
        not_english = {"original_language": {"$nin": ["en", None]}}
        rows = self.aggregate("movies", [
            {"$match": {**not_english, "$or": [us_country, us_company]}},
            {"$sort": {"vote_count": DESCENDING, "_id": 1}},  # the example is the most voted movie
            {"$group": {"_id": "$original_language",
                        "movies": {"$sum": 1},
                        "example_title": {"$first": "$title"},
                        "example_vote_count": {"$first": "$vote_count"}}},
            {"$sort": {"movies": DESCENDING, "_id": 1}},
            {"$limit": 10},
        ])
        total = self.db.movies.count_documents({**not_english, "$or": [us_country, us_company]})
        only_company = self.db.movies.count_documents({**not_english, **us_company,
                                                       "production_countries.iso_3166_1": {"$ne": "US"}})
        print("Matching movies: {:,} ({} only through a company name with 'United States').\n"
              .format(total, only_company))
        print_first_document(rows)
        print_table([[rank, r["_id"], r["movies"], r["example_title"], r["example_vote_count"]]
                     for rank, r in enumerate(rows, start=1)],
                    ["rank", "original_language", "movies", "example_title", "example_vote_count"])

    def task10(self):
        """For each user: number of ratings, population variance of the ratings and
        number of distinct genres rated. Top 10 users by distinct genres and by
        variance (users with >= 20 ratings)."""
        started = time.time()
        n_genres = len(self.db.movies.distinct("genres"))
        self.aggregate("ratings", [
            {"$group": {"_id": "$user_id",
                        "ratings": {"$sum": 1},
                        "std_dev": {"$stdDevPop": "$rating"},
                        "movie_ids": {"$addToSet": "$movie_id"}}},
            {"$lookup": {"from": "movies", "localField": "movie_ids", "foreignField": "_id", "as": "rated_movies",
                         "pipeline": [{"$project": {"_id": 0, "genres": 1}}]}},
            {"$project": {"ratings": 1,
                          # rounded so that equal variances are not ordered by floating-point noise
                          "variance": {"$round": [{"$pow": ["$std_dev", 2]}, 6]},
                          "distinct_genres": {"$size": {"$reduce": {"input": "$rated_movies.genres", "initialValue": [],
                                                                    "in": {"$setUnion": ["$$value", "$$this"]}}}}}},
            {"$out": "user_rating_stats"},
        ])
        stats = self.db.user_rating_stats
        print("Statistics for {:,} users written to the collection user_rating_stats ({:.0f} s).".format(
            stats.count_documents({}), time.time() - started))
        active = {"ratings": {"$gte": 20}}
        print("Users with >= 20 ratings: {:,}, of these with all {} genres: {:,}\n".format(
            stats.count_documents(active), n_genres, stats.count_documents({**active, "distinct_genres": n_genres})))

        headers = ["rank", "user_id", "ratings", "variance", "distinct_genres"]
        diverse = list(stats.find(active).sort([("distinct_genres", DESCENDING), ("ratings", 1), ("_id", 1)]).limit(10))
        print_first_document(diverse)
        print("Top 10 most genre-diverse users (ties: fewer ratings first):")
        print_table([[rank, r["_id"], r["ratings"], r["variance"], r["distinct_genres"]]
                     for rank, r in enumerate(diverse, start=1)], headers, floatfmt=".4f")
        varied = list(stats.find(active).sort([("variance", DESCENDING), ("ratings", DESCENDING), ("_id", 1)]).limit(10))
        print("\nUsers with >= 20 ratings at the highest possible variance 5.0625 (half 0.5, half 5.0): {:,}".format(
            stats.count_documents({**active, "variance": 5.0625})))
        print("Top 10 highest-variance users (ties: more ratings first):")
        print_table([[rank, r["_id"], r["ratings"], r["variance"], r["distinct_genres"]]
                     for rank, r in enumerate(varied, start=1)], headers, floatfmt=".4f")
        save_csv("task10_user_rating_stats.csv", headers[1:],
                 [[r["_id"], r["ratings"], r["variance"], r["distinct_genres"]] for r in stats.find().sort("_id", 1)])


def main():
    program = None
    try:
        program = MovieQueries()
        tasks = [
            ("1", "Considering only crew with job = Director, which 10 directors with >= 5 movies have the "
                  "highest median revenue? Also report each director's movie count and mean vote_average.",
             program.task1),
            ("2", "List actor pairs that have co-starred in >= 3 movies together, their number of "
                  "co-appearances, and their average movie vote_average. Sort by number of co-appearances.",
             program.task2),
            ("3", "List the top 10 actors (with >= 10 credited movies) that have the widest genre breadth. "
                  "Report the actor, the number of distinct genres they've appeared in, and up to 5 example "
                  "genres.", program.task3),
            ("4", "For film collections (belongs_to_collection.name not null) with >= 3 movies, which 10 "
                  "collections have the largest total revenue? For each, report movie count, total revenue, "
                  "median vote_average, and the earliest -> latest release date.", program.task4),
            ("5", "By decade and primary genre (first element in genres), what is the median runtime and "
                  "movie count? List results sorted by decade then median runtime (desc).", program.task5),
            ("6", "For each movie's top-billed 5 cast (by order), what is the proportion of female cast? "
                  "Aggregate by decade and list decades sorted by average female proportion (desc), including "
                  "movie counts used. Unknown gender may be ignored.", program.task6),
            ("7", "Using a text search over overview and tagline, which 20 movies matching \"noir\" or "
                  "\"neo-noir\" (and vote_count >= 50) have the highest vote_average? Return title, year, "
                  "vote_average, and vote_count.", program.task7),
            ("8", "Which 20 director-actor pairs with >= 3 collaborations (same movie) have the highest mean "
                  "vote_average, considering only movies with vote_count >= 100? Include the pair's films "
                  "count and mean revenue.", program.task8),
            ("9", "Among movies where original_language != \"en\" but at least one production company or "
                  "country is United States, which are the top 10 original languages by count? For each "
                  "language, report the count and one example title.", program.task9),
            ("10", "For each user, what is their ratings count, population variance of ratings, and number of "
                   "distinct genres rated? List the top 10 most genre-diverse users, and separately the top 10 "
                   "highest-variance users (only users with >= 20 ratings).", program.task10),
        ]
        for name, question, task in tasks:
            print("\n" + "=" * 78)
            print(textwrap.fill("Task %s: %s" % (name, question), width=78))
            print("=" * 78)
            started = time.time()
            task()
            print("[task %s took %.1f s]" % (name, time.time() - started))
    except Exception as e:
        print("ERROR: Failed to use database:", e)
        raise
    finally:
        if program:
            program.connection.close_connection()


if __name__ == "__main__":
    main()
