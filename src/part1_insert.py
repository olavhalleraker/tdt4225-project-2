"""
Part 1.2 - Create the collections and insert the cleaned movie data into MongoDB.

Run:  python part1_insert.py | tee ../output/part1_insert.txt
"""
import time
from collections import defaultdict
from pprint import pprint

from pymongo import ASCENDING, TEXT
from tabulate import tabulate

import cleaning
from DbConnector import DbConnector

# Validation rules, checked by MongoDB for every inserted document. Missing
# values are stored as null (or [] for lists), never as 0 or "".
MOVIE_SCHEMA = {
    "bsonType": "object",
    "required": ["_id", "title", "release_date", "runtime", "budget", "revenue", "vote_average",
                 "vote_count", "genres", "belongs_to_collection", "keywords", "cast", "crew", "movielens_ids"],
    "properties": {
        "_id": {"bsonType": "int"},
        "title": {"bsonType": ["string", "null"]},
        "release_date": {"bsonType": ["date", "null"]},
        "runtime": {"bsonType": ["int", "null"], "minimum": 1},
        "budget": {"bsonType": ["int", "long", "null"], "minimum": cleaning.MIN_MONEY_USD},
        "revenue": {"bsonType": ["int", "long", "null"], "minimum": cleaning.MIN_MONEY_USD},
        "vote_average": {"bsonType": ["double", "null"], "minimum": 0.5, "maximum": 10},
        "vote_count": {"bsonType": "int", "minimum": 0},
        "genres": {"bsonType": "array", "items": {"bsonType": "string"}},
        "belongs_to_collection": {"bsonType": ["object", "null"], "required": ["id", "name"]},
        "keywords": {"bsonType": "array", "items": {"bsonType": "string"}},
        "cast": {"bsonType": "array", "items": {
            "bsonType": "object", "required": ["id", "name", "gender", "order"],
            "properties": {"id": {"bsonType": "int"}, "gender": {"enum": ["female", "male", None]},
                           "order": {"bsonType": "int"}}}},
        "crew": {"bsonType": "array", "items": {
            "bsonType": "object", "required": ["id", "name", "job", "gender"],
            "properties": {"id": {"bsonType": "int"}, "gender": {"enum": ["female", "male", None]}}}},
        "movielens_ids": {"bsonType": "array", "items": {"bsonType": "int"}},
    },
}

RATING_SCHEMA = {
    "bsonType": "object",
    "required": ["user_id", "movie_id", "movielens_id", "rating", "rated_at"],
    "properties": {
        "user_id": {"bsonType": "int"},
        "movie_id": {"bsonType": ["int", "null"]},
        "movielens_id": {"bsonType": "int"},
        "rating": {"bsonType": "double", "minimum": 0.5, "maximum": 5},
        "rated_at": {"bsonType": "date"},
    },
}

MOVIES_PER_BATCH = 1000
RATINGS_PER_BATCH = 50000


class MovieInserter:

    def __init__(self):
        self.connection = DbConnector()
        self.client = self.connection.client
        self.db = self.connection.db
        self.movie_ids = set()

    def create_collections(self):
        for name, schema in (("movies", MOVIE_SCHEMA), ("ratings", RATING_SCHEMA)):
            self.db.drop_collection(name)
            self.db.create_collection(name, validator={"$jsonSchema": schema})
        print("Created collections movies and ratings (with $jsonSchema validators)")

    def insert_movies(self):
        """One document per movie, with credits, keywords and MovieLens ids embedded."""
        started = time.time()
        movies = cleaning.read_movies()
        credits = cleaning.read_credits()
        keywords = cleaning.read_keywords()
        movielens_ids = defaultdict(list)
        for movielens_id, tmdb_id in cleaning.read_links().items():
            if tmdb_id in movies:
                movielens_ids[tmdb_id].append(movielens_id)

        batch = []
        for movie in movies.values():
            movie["keywords"] = keywords.get(movie["_id"], [])
            movie["cast"], movie["crew"] = credits.get(movie["_id"], ([], []))
            movie["movielens_ids"] = sorted(movielens_ids.get(movie["_id"], []))
            batch.append(movie)
            if len(batch) == MOVIES_PER_BATCH:
                self.db.movies.insert_many(batch)
                batch = []
        if batch:
            self.db.movies.insert_many(batch)
        self.movie_ids = set(movies)

        print("\nInserted %s movies in %.0f s" % (f"{len(movies):,}", time.time() - started))
        print(tabulate([["Movies", f"{len(movies):,}"],
                        ["Movies with a credits / keywords row",
                         "%s / %s" % (f"{sum(1 for m in movies if m in credits):,}",
                                      f"{sum(1 for m in movies if m in keywords):,}")],
                        ["Movies with non-empty cast / crew / keywords",
                         "%s / %s / %s" % (f"{sum(1 for m in movies.values() if m['cast']):,}",
                                           f"{sum(1 for m in movies.values() if m['crew']):,}",
                                           f"{sum(1 for m in movies.values() if m['keywords']):,}")],
                        ["Movies with at least one MovieLens id", f"{len(movielens_ids):,}"],
                        ["Credits rows without a movie (not inserted)", len(set(credits) - set(movies))],
                        ["Keyword rows without a movie (not inserted)", len(set(keywords) - set(movies))]],
                       tablefmt="simple"))

    def insert_ratings(self):
        """One document per rating. movie_id references movies._id (the TMDB id) and
        is null when the MovieLens movie cannot be linked to a movie."""
        started = time.time()
        links = cleaning.read_links()
        stats = {"Ratings inserted": 0, "Linked to a movie": 0, "movie_id null: no tmdbId": 0,
                 "movie_id null: tmdbId not in movies": 0}
        batch = []
        for user_id, movielens_id, rating, timestamp in cleaning.read_ratings():
            tmdb_id = links.get(movielens_id)
            if tmdb_id is None:
                stats["movie_id null: no tmdbId"] += 1
            elif tmdb_id not in self.movie_ids:
                stats["movie_id null: tmdbId not in movies"] += 1
                tmdb_id = None
            else:
                stats["Linked to a movie"] += 1
            batch.append({"user_id": user_id, "movie_id": tmdb_id, "movielens_id": movielens_id,
                          "rating": rating, "rated_at": cleaning.parse_timestamp(timestamp)})
            if len(batch) == RATINGS_PER_BATCH:
                self.db.ratings.insert_many(batch, ordered=False)
                stats["Ratings inserted"] += len(batch)
                batch = []
                if stats["Ratings inserted"] % 5000000 == 0:
                    print("  %10s ratings inserted (%.0f s)" % (f"{stats['Ratings inserted']:,}", time.time() - started))
        if batch:
            self.db.ratings.insert_many(batch, ordered=False)
            stats["Ratings inserted"] += len(batch)

        print("\nInserted ratings in %.1f minutes" % ((time.time() - started) / 60))
        print(tabulate([[k, f"{v:,}"] for k, v in stats.items()], headers=["Step", "Count"], tablefmt="simple"))

    def create_indexes(self):
        started = time.time()
        # Text index for the "noir" search in task 7
        self.db.movies.create_index([("overview", TEXT), ("tagline", TEXT)], name="overview_tagline_text",
                                    default_language="english")
        # One rating per user and MovieLens movie. The unique index enforces this
        # (schema-on-write) and serves lookups by user_id (left prefix). Note that the
        # $group per user in task 10 does not use it: it scans the whole collection.
        self.db.ratings.create_index([("user_id", ASCENDING), ("movielens_id", ASCENDING)],
                                     name="user_movielens_unique", unique=True)
        print("\nCreated indexes in %.0f s" % (time.time() - started))

    def show_result(self):
        print("\nDocuments per collection:")
        rows = []
        for name in ("movies", "ratings"):
            stats = self.db.command("collStats", name)
            rows.append([name, f"{stats['count']:,}", "%.0f" % stats["avgObjSize"], "%.1f" % (stats["size"] / 1e6),
                         "%.1f" % (stats["storageSize"] / 1e6), ", ".join(self.db[name].index_information())])
        print(tabulate(rows, headers=["Collection", "Documents", "Avg. bytes", "Data MB", "Storage MB", "Indexes"],
                       tablefmt="simple"))

        print("\ndb.movies.find_one({'_id': 862}) with cast, crew and keywords cut to the first entries:")
        pprint(self.db.movies.find_one({"_id": 862}, {"cast": {"$slice": 2}, "crew": {"$slice": 2},
                                                      "keywords": {"$slice": 4}}), sort_dicts=False)
        print("\nA repaired movie with unknown values (null), db.movies.find_one({'_id': 82663}):")
        pprint(self.db.movies.find_one({"_id": 82663}, {"overview": 0, "cast": {"$slice": 1}, "crew": {"$slice": 1}}),
               sort_dicts=False)
        print("\ndb.ratings.find_one({'user_id': 1}):")
        pprint(self.db.ratings.find_one({"user_id": 1}), sort_dicts=False)


def main():
    program = None
    try:
        program = MovieInserter()
        program.create_collections()
        program.insert_movies()
        program.insert_ratings()
        program.create_indexes()
        program.show_result()
    except Exception as e:
        print("ERROR: Failed to use database:", e)
        raise
    finally:
        if program:
            program.connection.close_connection()


if __name__ == "__main__":
    main()
