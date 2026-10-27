"""
Shared parsing and cleaning rules (used by both the EDA and the insert program).
"""
import ast
import csv
import os
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MOVIES_CSV = os.path.join(DATA_DIR, "movies_metadata.csv")
CREDITS_CSV = os.path.join(DATA_DIR, "credits.csv")
KEYWORDS_CSV = os.path.join(DATA_DIR, "keywords.csv")
LINKS_CSV = os.path.join(DATA_DIR, "links.csv")
RATINGS_CSV = os.path.join(DATA_DIR, "ratings.csv")

MOVIE_COLUMNS = ["adult", "belongs_to_collection", "budget", "genres", "homepage", "id", "imdb_id",
                 "original_language", "original_title", "overview", "popularity", "poster_path",
                 "production_companies", "production_countries", "release_date", "revenue", "runtime",
                 "spoken_languages", "status", "tagline", "title", "video", "vote_average", "vote_count"]

# Budget and revenue are 0 when unknown. In addition, a few hundred movies have
# amounts such as 1, 4 or 25 (e.g. 'A Farewell to Arms': budget 4, revenue 25),
# which are not dollar amounts but probably millions. Amounts below this limit
# are therefore treated as unknown as well.
MIN_MONEY_USD = 1000

# Overviews that only say that there is no overview.
OVERVIEW_PLACEHOLDERS = {"No overview found.", "No Overview", "No overview yet."}

# TMDB gender codes. 0 means that the gender is not set and becomes None.
GENDER = {1: "female", 2: "male"}


def read_movie_rows(path=MOVIES_CSV, repaired=None):
    """Yield the rows of movies_metadata.csv as lists of 24 fields.

    Three overviews contain a line break outside quotes, which splits the movie
    into a row with 10 fields (adult .. first part of the overview) and a row
    with 15 fields (rest of the overview .. vote_count). Read as they are, the
    second row has a date as id and production companies as genres. The two
    parts are joined into one row again. If `repaired` is a list, the ids of
    the repaired movies are appended to it."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == MOVIE_COLUMNS, "Unexpected CSV header: %s" % header
        for row in reader:
            if len(row) == 10:
                rest = next(reader)
                assert len(rest) == 15, "Cannot repair the row of movie %s" % row[5]
                # The line break separated two words, so join the parts with a space
                row = row[:9] + [row[9].rstrip() + " " + rest[0].lstrip()] + rest[1:]
                if repaired is not None:
                    repaired.append(int(row[5]))
            assert len(row) == len(MOVIE_COLUMNS), "Row with %d fields" % len(row)
            yield row


def parse_literal(text):
    """The nested columns (genres, cast, ...) are written as Python literals with
    single quotes, not as JSON, so they are parsed with ast.literal_eval.
    An empty field gives None."""
    return ast.literal_eval(text) if text.strip() else None


def none_if_empty(text):
    text = text.strip()
    return text or None


def parse_date(text):
    """'YYYY-MM-DD' -> datetime at 00:00, stored as a BSON date. Empty -> None."""
    return datetime.strptime(text, "%Y-%m-%d") if text else None


def parse_money(text):
    """Budget/revenue in USD. None when unknown (0) or implausibly small."""
    amount = int(float(text or 0))
    return amount if amount >= MIN_MONEY_USD else None


def parse_timestamp(unix_seconds):
    """Unix time -> naive datetime in UTC (pymongo stores naive datetimes as UTC)."""
    return datetime.fromtimestamp(int(unix_seconds), tz=timezone.utc).replace(tzinfo=None)


def build_movie(row):
    """Turn one row of movies_metadata.csv into a movie document, without the
    credits, keywords and MovieLens ids that come from the other files.

    Missing values become None: empty strings, budget/revenue/runtime 0, a
    vote_average of 0 (no votes, or below the lowest possible average 0.5) and
    placeholder overviews. Nested columns keep only the fields that carry
    information (e.g. genre names, but not genre ids or poster paths)."""
    m = dict(zip(MOVIE_COLUMNS, row))
    vote_count = int(float(m["vote_count"]))
    vote_average = float(m["vote_average"])
    runtime = int(float(m["runtime"] or 0))
    overview = none_if_empty(m["overview"])
    collection = parse_literal(m["belongs_to_collection"])
    return {
        "_id": int(m["id"]),
        "imdb_id": none_if_empty(m["imdb_id"]),
        "title": none_if_empty(m["title"]),
        "original_title": none_if_empty(m["original_title"]),
        "original_language": none_if_empty(m["original_language"]),
        "overview": None if overview in OVERVIEW_PLACEHOLDERS else overview,
        "tagline": none_if_empty(m["tagline"]),
        "status": none_if_empty(m["status"]),
        "release_date": parse_date(m["release_date"]),
        "runtime": runtime or None,
        "budget": parse_money(m["budget"]),
        "revenue": parse_money(m["revenue"]),
        "vote_average": vote_average if vote_count > 0 and vote_average > 0 else None,
        "vote_count": vote_count,
        "popularity": float(m["popularity"]),
        "adult": m["adult"] == "True",
        "video": m["video"] == "True",
        "homepage": none_if_empty(m["homepage"]),
        "genres": [g["name"] for g in parse_literal(m["genres"]) or []],
        "belongs_to_collection": {"id": collection["id"], "name": collection["name"]} if collection else None,
        "production_companies": [{"id": c["id"], "name": c["name"]}
                                 for c in parse_literal(m["production_companies"]) or []],
        "production_countries": [{"iso_3166_1": c["iso_3166_1"], "name": c["name"]}
                                 for c in parse_literal(m["production_countries"]) or []],
        "spoken_languages": [{"iso_639_1": s["iso_639_1"], "name": s["name"]}
                             for s in parse_literal(m["spoken_languages"]) or []],
    }


def read_movies(path=MOVIES_CSV):
    """Read, repair and deduplicate movies_metadata.csv.

    29 ids occur more than once. The copies are identical or differ only in
    popularity and vote_count (snapshots taken at different times), so we keep
    the copy with the highest vote_count (the first one on ties).

    Returns {movie id: movie document}."""
    movies = {}
    for row in read_movie_rows(path):
        movie = build_movie(row)
        kept = movies.get(movie["_id"])
        if kept is None or movie["vote_count"] > kept["vote_count"]:
            movies[movie["_id"]] = movie
    return movies


def build_cast(cast):
    """Keep id, name, character, gender and billing order of each cast member."""
    return [{"id": c["id"], "name": c["name"], "character": c["character"] or None,
             "gender": GENDER.get(c["gender"]), "order": c["order"]} for c in cast]


def build_crew(crew):
    """Keep id, name, job, department and gender of each crew member."""
    return [{"id": c["id"], "name": c["name"], "job": c["job"], "department": c["department"],
             "gender": GENDER.get(c["gender"])} for c in crew]


def read_credits(path=CREDITS_CSV):
    """Read credits.csv. 43 movie ids occur more than once (44 extra rows); the copies have the same cast
    and the same crew members (only the order of the crew list differs in 7
    cases), so the first copy is kept.

    Returns {movie id: (cast, crew)}."""
    credits = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        assert next(reader) == ["cast", "crew", "id"]
        for cast, crew, movie_id in reader:
            if int(movie_id) not in credits:
                credits[int(movie_id)] = (build_cast(parse_literal(cast)), build_crew(parse_literal(crew)))
    return credits


def read_keywords(path=KEYWORDS_CSV):
    """Read keywords.csv. The 987 duplicate rows are exact copies, so the first
    copy is kept. Returns {movie id: [keyword names]}."""
    keywords = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        assert next(reader) == ["id", "keywords"]
        for movie_id, words in reader:
            keywords.setdefault(int(movie_id), [k["name"] for k in parse_literal(words)])
    return keywords


def read_links(path=LINKS_CSV):
    """Read links.csv. Returns {MovieLens id: TMDB id, or None when tmdbId is empty}."""
    links = {}
    with open(path, newline="") as f:
        reader = csv.reader(f)
        assert next(reader) == ["movieId", "imdbId", "tmdbId"]
        for movielens_id, _imdb_id, tmdb_id in reader:
            links[int(movielens_id)] = int(tmdb_id) if tmdb_id else None
    return links


def read_ratings(path=RATINGS_CSV):
    """Yield (user_id, movielens_id, rating, unix_timestamp) one row at a time
    (ratings.csv has 26 million rows, so it is streamed)."""
    with open(path, newline="") as f:
        reader = csv.reader(f)
        assert next(reader) == ["userId", "movieId", "rating", "timestamp"]
        for user_id, movielens_id, rating, timestamp in reader:
            yield int(user_id), int(movielens_id), float(rating), int(timestamp)
