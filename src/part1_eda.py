"""
Part 1.1 - Exploratory data analysis (EDA) of The Movies Dataset.

Run:  python part1_eda.py | tee ../output/part1_eda.txt
"""
import csv
import os
from collections import Counter, defaultdict
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from tabulate import tabulate

import cleaning

FIGURE_DIR = os.path.join(os.path.dirname(__file__), "..", "report", "figures")

FILES = ["movies_metadata.csv", "credits.csv", "keywords.csv", "links.csv", "links_small.csv",
         "ratings.csv", "ratings_small.csv"]
LIST_COLUMNS = ["genres", "production_companies", "production_countries", "spoken_languages"]

# Chart colours
BLUE, ORANGE, GREEN = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK_2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
THOUSANDS = FuncFormatter(lambda value, _: f"{value:,.0f}")


def heading(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def table(rows, headers=(), **kwargs):
    print(tabulate(rows, headers=headers, tablefmt="simple", **kwargs))


def pct(part, whole):
    return 100.0 * part / whole if whole else 0.0


def percentile(sorted_values, p):
    if not sorted_values:
        return None
    return sorted_values[min(len(sorted_values) - 1, int(p / 100 * len(sorted_values)))]


def column(row, name):
    """Value of a column in a raw row of movies_metadata.csv."""
    return row[cleaning.MOVIE_COLUMNS.index(name)]


def number(row, name):
    return float(column(row, name) or 0)


def year(movie):
    return movie["release_date"].year if movie["release_date"] else None


class EDA:
    def __init__(self):
        self.rows = []         # rows of movies_metadata.csv after repairing the split ones
        self.raw = {}          # movie id -> raw row of the copy that is kept
        self.movies = {}       # movie id -> cleaned movie document (as inserted)
        self.credits = {}      # movie id -> (cast, crew) after cleaning
        self.decades = Counter()
        self.gender_by_position = defaultdict(Counter)
        self.ratings_per_user = Counter()
        self.rating_values = Counter()

    def run(self):
        self.files()
        self.split_rows()
        self.duplicate_movies()
        self.missing_values()
        self.numeric_attributes()
        self.suspicious_values()
        self.categorical_attributes()
        self.release_dates()
        self.genres()
        self.collections()
        self.companies_countries_languages()
        self.credits_file()
        self.cast_and_crew()
        self.keywords_file()
        self.links_file()
        self.ratings_file()
        self.figures()

    # ------------------------------------------------------------------ #
    def files(self):
        heading("1. Files")
        rows = []
        for name in FILES:
            path = os.path.join(cleaning.DATA_DIR, name)
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader)
                n_rows = sum(1 for _ in reader)
            rows.append([name, "%.1f" % (os.path.getsize(path) / 1e6), f"{n_rows:,}", len(header),
                         ", ".join(header)])
        table(rows, ["File", "MB", "CSV rows", "Columns", "Column names"], maxcolwidths=[None, None, None, None, 46])

    def split_rows(self):
        heading("2. movies_metadata.csv - rows split by a line break in the overview")
        lengths = Counter()
        second_parts = []
        with open(cleaning.MOVIES_CSV, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                lengths[len(row)] += 1
                if len(row) == 15:
                    second_parts.append(row)
        table([[k, f"{v:,}"] for k, v in sorted(lengths.items())], ["Fields in CSV row", "Rows"])
        print("\nThe 15-field rows read with the 24 column names (all columns are shifted):")
        table([[column(r, "id"), column(r, "adult")[:30], column(r, "genres")[:48], column(r, "original_language")]
               for r in second_parts], ["id", "adult", "genres", "original_language"])

        repaired = []
        self.rows = list(cleaning.read_movie_rows(repaired=repaired))
        by_id = {int(column(r, "id")): r for r in self.rows}
        print("\nAfter joining each 10-field row with the 15-field row that follows it:")
        table([[movie_id, column(by_id[movie_id], "title"), column(by_id[movie_id], "release_date"),
                ", ".join(g["name"] for g in cleaning.parse_literal(column(by_id[movie_id], "genres")))]
               for movie_id in repaired], ["id", "title", "release_date", "genres"])
        print("-> %d movies repaired, %s movie rows in total." % (len(repaired), f"{len(self.rows):,}"))

    def duplicate_movies(self):
        heading("3. movies_metadata.csv - duplicate ids")
        groups = defaultdict(list)
        for row in self.rows:
            groups[int(column(row, "id"))].append(row)
        dups = {k: g for k, g in groups.items() if len(g) > 1}
        differs = Counter()
        for g in dups.values():
            for i, name in enumerate(cleaning.MOVIE_COLUMNS):
                if len({r[i] for r in g}) > 1:
                    differs[name] += 1
        identical = [k for k, g in dups.items() if all(r == g[0] for r in g)]
        table([["Movie rows", f"{len(self.rows):,}"],
               ["Unique ids", f"{len(groups):,}"],
               ["Ids that occur more than once", len(dups)],
               ["Extra (duplicate) rows", sum(len(g) - 1 for g in dups.values())],
               ["Duplicate groups that are exact copies", len(identical)]] +
              [["Groups where %s differs" % name, n] for name, n in differs.most_common()])

        # The copy that cleaning.read_movies keeps: highest vote_count, the first one on ties
        for row in self.rows:
            movie_id = int(column(row, "id"))
            if movie_id not in self.raw or number(row, "vote_count") > number(self.raw[movie_id], "vote_count"):
                self.raw[movie_id] = row
        self.movies = cleaning.read_movies()
        assert self.movies.keys() == self.raw.keys()

        print("\nExamples of copies that differ (kept = highest vote_count, the first one on ties):")
        examples = []
        for movie_id in [k for k in dups if k not in identical][:4]:
            for r in dups[movie_id]:
                examples.append([movie_id, column(r, "title"), column(r, "vote_count"), column(r, "popularity"),
                                 "kept" if r is self.raw[movie_id] else "dropped"])
        table(examples, ["id", "title", "vote_count", "popularity", "Decision"], disable_numparse=True)
        print("-> %s unique movies are inserted." % f"{len(self.movies):,}")

    def missing_values(self):
        heading("4. movies_metadata.csv - missing values per column (after repair and deduplication)")
        coded_missing = {   # values that are not empty but still mean "unknown"
            "budget": lambda v: float(v) == 0,
            "revenue": lambda v: float(v) == 0,
            "runtime": lambda v: v != "" and float(v) == 0,
            "vote_average": lambda v: float(v) == 0,
            "vote_count": lambda v: float(v) == 0,
            "overview": lambda v: v.strip() in cleaning.OVERVIEW_PLACEHOLDERS,
        }
        for name in LIST_COLUMNS:
            coded_missing[name] = lambda v: v.strip() == "[]"
        n = len(self.raw)
        rows = []
        for i, name in enumerate(cleaning.MOVIE_COLUMNS):
            empty = sum(1 for r in self.raw.values() if r[i].strip() == "")
            is_coded = coded_missing.get(name, lambda v: False)
            coded = sum(1 for r in self.raw.values() if r[i].strip() != "" and is_coded(r[i]))
            key = "_id" if name == "id" else name
            if name == "poster_path":
                stored = "-"
            elif name == "vote_count":
                stored = "0 kept"
            else:
                stored = sum(1 for m in self.movies.values() if m[key] is None or m[key] == [])
            rows.append([name, f"{empty:,}", f"{coded:,}", stored if isinstance(stored, str) else f"{stored:,}",
                         "" if isinstance(stored, str) else "%.1f %%" % pct(stored, n)])
        table(rows, ["Column", "Empty", "0 / [] / placeholder", "Stored as None or []", "Share"])
        print("budget/revenue: also None when below %d USD. vote_average: None when 0 (no votes or 0 with votes)."
              % cleaning.MIN_MONEY_USD)
        print("poster_path is not stored. Placeholders: %s" % ", ".join(sorted(cleaning.OVERVIEW_PLACEHOLDERS)))

    def numeric_attributes(self):
        heading("5. movies_metadata.csv - numeric attributes (known values after cleaning)")
        rows = []
        for key, fmt in [("budget", ",.0f"), ("revenue", ",.0f"), ("runtime", ",.0f"),
                         ("vote_average", ".1f"), ("vote_count", ",.0f"), ("popularity", ".2f")]:
            values = sorted(m[key] for m in self.movies.values() if m[key] is not None)
            stats = [values[0], percentile(values, 25), percentile(values, 50), percentile(values, 75),
                     values[-1], sum(values) / len(values)]
            rows.append([key, f"{len(values):,}"] + [format(x, fmt) for x in stats])
        table(rows, ["Attribute", "Known", "min", "p25", "median", "p75", "max", "mean"])
        print("budget/revenue in USD, runtime in minutes. vote_count includes the movies with 0 votes.")

    def suspicious_values(self):
        heading("6. movies_metadata.csv - suspicious values")
        raw = list(self.raw.values())
        limit = cleaning.MIN_MONEY_USD
        tiny = [r for r in raw if 0 < number(r, "budget") < limit or 0 < number(r, "revenue") < limit]
        zero_avg = Counter(int(number(r, "vote_count")) for r in raw
                           if number(r, "vote_count") > 0 and number(r, "vote_average") == 0)
        long_runtime = sorted((r for r in raw if number(r, "runtime") > 360), key=lambda r: -number(r, "runtime"))
        table([["Budget > 0 but below %s USD" % f"{limit:,}", sum(1 for r in raw if 0 < number(r, "budget") < limit)],
               ["Revenue > 0 but below %s USD" % f"{limit:,}", sum(1 for r in raw if 0 < number(r, "revenue") < limit)],
               ["Budget 1,000 to 9,999 USD (kept)", sum(1 for r in raw if limit <= number(r, "budget") < 10000)],
               ["Revenue 1,000 to 9,999 USD (kept)", sum(1 for r in raw if limit <= number(r, "revenue") < 10000)],
               ["vote_average 0 although vote_count > 0", sum(zero_avg.values())],
               ["vote_average 0 with only 1 vote", zero_avg[1]],
               ["Lowest vote_average above 0", min(number(r, "vote_average") for r in raw
                                                    if number(r, "vote_average") > 0)],
               ["Runtime above 6 hours (kept)", len(long_runtime)],
               ["Movies marked adult", sum(1 for r in raw if column(r, "adult") == "True")]])
        print("\nTiny budgets/revenues, the most voted movies (set to None, i.e. unknown):")
        tiny.sort(key=lambda r: -number(r, "vote_count"))
        table([[column(r, "title"), column(r, "release_date")[:4], column(r, "budget"), column(r, "revenue"),
                column(r, "vote_count")] for r in tiny[:8]],
              ["title", "year", "budget", "revenue", "vote_count"], disable_numparse=True)
        print("\nLongest runtimes (mostly TV mini-series, kept):")
        table([[column(r, "title"), column(r, "release_date")[:4], int(number(r, "runtime"))] for r in long_runtime[:6]],
              ["title", "year", "runtime (min)"])

    def categorical_attributes(self):
        heading("7. movies_metadata.csv - categorical attributes")
        n = len(self.movies)
        status = Counter(m["status"] or "(missing)" for m in self.movies.values())
        table([[s, f"{c:,}", "%.2f %%" % pct(c, n)] for s, c in status.most_common()], ["status", "Movies", "Share"])
        print()
        languages = Counter(m["original_language"] or "(missing)" for m in self.movies.values())
        print("original_language: %d distinct codes. The 10 most common:" % (len(languages) - 1))
        table([[lang, f"{c:,}", "%.1f %%" % pct(c, n)] for lang, c in languages.most_common(10)],
              ["original_language", "Movies", "Share"])
        print("Missing original_language: %d" % languages["(missing)"])
        print()
        table([["adult", sum(m["adult"] for m in self.movies.values())],
               ["video", sum(m["video"] for m in self.movies.values())]], ["Flag", "Movies with True"])

    def release_dates(self):
        heading("8. movies_metadata.csv - release_date")
        dates = sorted(m["release_date"] for m in self.movies.values() if m["release_date"])
        last_rating = datetime(2017, 8, 4)
        later = Counter(m["status"] for m in self.movies.values()
                        if m["release_date"] and m["release_date"] > last_rating)
        table([["Movies with release_date", f"{len(dates):,}"],
               ["Missing release_date", len(self.movies) - len(dates)],
               ["Earliest", dates[0].date()],
               ["Latest", dates[-1].date()],
               ["Release date after the last rating (2017-08-04)", sum(later.values())],
               ["Release date after the last rating, status Released", later["Released"]]])
        for movie in self.movies.values():
            if movie["release_date"]:
                self.decades[year(movie) // 10 * 10] += 1
        print()
        table([["%ds" % d, f"{c:,}"] for d, c in sorted(self.decades.items())], ["Decade", "Movies"])

    def genres(self):
        heading("9. movies_metadata.csv - genres")
        n = len(self.movies)
        any_genre = Counter(g for m in self.movies.values() for g in m["genres"])
        first_genre = Counter(m["genres"][0] for m in self.movies.values() if m["genres"])
        per_movie = Counter(min(len(m["genres"]), 5) for m in self.movies.values())
        print("%d distinct genres (after repairing the split rows):" % len(any_genre))
        table([[g, f"{c:,}", "%.1f %%" % pct(c, n), f"{first_genre[g]:,}"] for g, c in any_genre.most_common()],
              ["Genre", "Movies", "Share", "As first genre"])
        print()
        table([["5+" if k == 5 else k, f"{c:,}"] for k, c in sorted(per_movie.items())], ["Genres per movie", "Movies"])

    def collections(self):
        heading("10. movies_metadata.csv - belongs_to_collection")
        sizes = Counter(m["belongs_to_collection"]["id"] for m in self.movies.values() if m["belongs_to_collection"])
        names = defaultdict(set)
        for m in self.movies.values():
            if m["belongs_to_collection"]:
                names[m["belongs_to_collection"]["id"]].add(m["belongs_to_collection"]["name"])
        size_groups = Counter("1" if s == 1 else "2" if s == 2 else "3-5" if s <= 5 else "6-10" if s <= 10 else "> 10"
                              for s in sizes.values())
        table([["Movies in a collection", f"{sum(sizes.values()):,}"],
               ["Distinct collections", f"{len(sizes):,}"],
               ["Collections with >= 3 movies", sum(1 for s in sizes.values() if s >= 3)],
               ["Collection ids with more than one name", sum(1 for v in names.values() if len(v) > 1)]])
        print()
        table([[g, size_groups[g]] for g in ["1", "2", "3-5", "6-10", "> 10"]], ["Movies in collection", "Collections"])
        print("\nLargest collections:")
        table([[next(iter(names[c])), s] for c, s in sizes.most_common(5)], ["Collection", "Movies"])

    def companies_countries_languages(self):
        heading("11. movies_metadata.csv - production companies, countries and spoken languages")
        n = len(self.movies)
        rows = []
        for key, value in [("production_companies", "name"), ("production_countries", "iso_3166_1"),
                           ("spoken_languages", "iso_639_1")]:
            counts = Counter(x[value] for m in self.movies.values() for x in m[key])
            empty = sum(1 for m in self.movies.values() if not m[key])
            rows.append([key, f"{len(counts):,}", f"{empty:,}", "%.1f %%" % pct(empty, n),
                         ", ".join("%s (%s)" % (k, f"{c:,}") for k, c in counts.most_common(3))])
        table(rows, ["Column", "Distinct", "Empty list", "Share", "Most common"], maxcolwidths=[None] * 4 + [50])

        us = [m for m in self.movies.values() if any(c["iso_3166_1"] == "US" for c in m["production_countries"])]
        us_not_english = sum(1 for m in us if m["original_language"] not in ("en", None))
        us_companies = Counter(c["name"] for m in self.movies.values() for c in m["production_companies"]
                               if "united states" in c["name"].lower())
        print()
        table([["Movies with United States as production country", f"{len(us):,}"],
               ["United States and original_language not 'en'", f"{us_not_english:,}"],
               ["Company names containing 'United States'", ", ".join("%s (%d)" % kc for kc in us_companies.items())]])
        print("-> Companies have only id and name, no country.")

    def credits_file(self):
        heading("12. credits.csv - rows and duplicates")
        groups = defaultdict(list)
        with open(cleaning.CREDITS_CSV, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            for cast, crew, movie_id in reader:
                groups[int(movie_id)].append((cast, crew))
        dups = {k: g for k, g in groups.items() if len(g) > 1}
        same_crew_members = 0
        for g in dups.values():
            members = [sorted(c["credit_id"] for c in cleaning.parse_literal(crew)) for _, crew in g]
            same_crew_members += all(m == members[0] for m in members)
        self.credits = cleaning.read_credits()
        table([["Rows", f"{sum(len(g) for g in groups.values()):,}"],
               ["Unique movie ids", f"{len(groups):,}"],
               ["Ids that occur more than once", len(dups)],
               ["Extra (duplicate) rows", sum(len(g) - 1 for g in dups.values())],
               ["Duplicate groups that are exact copies", sum(1 for g in dups.values() if all(x == g[0] for x in g))],
               ["Duplicate groups with the same cast", sum(1 for g in dups.values() if len({c for c, _ in g}) == 1)],
               ["Duplicate groups with the same crew members (credit_id)", same_crew_members],
               ["Credits for movie ids not in movies_metadata", len(set(groups) - set(self.movies))],
               ["Movies without a credits row", len(set(self.movies) - set(groups))]])

    def cast_and_crew(self):
        heading("13. credits.csv - cast and crew (after deduplication)")
        casts = [self.credits.get(m, ([], []))[0] for m in self.movies]
        crews = [self.credits.get(m, ([], []))[1] for m in self.movies]
        cast_sizes = sorted(len(c) for c in casts)
        crew_sizes = sorted(len(c) for c in crews)
        table([["Movies with empty cast", f"{cast_sizes.count(0):,}"],
               ["Movies with empty crew", f"{crew_sizes.count(0):,}"],
               ["Cast entries / median / max per movie",
                "%s / %d / %d" % (f"{sum(cast_sizes):,}", percentile(cast_sizes, 50), cast_sizes[-1])],
               ["Crew entries / median / max per movie",
                "%s / %d / %d" % (f"{sum(crew_sizes):,}", percentile(crew_sizes, 50), crew_sizes[-1])]])

        print("\nGender (TMDB code 0 = not set, stored as None):")
        all_cast = Counter(c["gender"] for cast in casts for c in cast)
        top5 = Counter()
        for cast in casts:
            for position, c in enumerate(sorted(cast, key=lambda c: c["order"])):
                if position < 5:
                    top5[c["gender"]] += 1
                if position < 10:
                    self.gender_by_position[position][c["gender"]] += 1
        all_crew = Counter(c["gender"] for crew in crews for c in crew)
        rows = []
        for label, counts in [("All cast entries", all_cast), ("Top-5 billed cast", top5), ("Crew entries", all_crew)]:
            total = sum(counts.values())
            rows.append([label, f"{total:,}"] + ["%.1f %%" % pct(counts[g], total) for g in ("female", "male", None)])
        table(rows, ["", "Entries", "female", "male", "unknown"])

        orders = Counter()
        for cast in casts:
            o = [c["order"] for c in cast]
            orders["consecutive 0..n-1" if o == list(range(len(o))) else
                   "duplicate order values" if len(set(o)) < len(o) else "gaps or other start"] += 1
        repeated = sum(1 for cast in casts if len({c["id"] for c in cast}) < len(cast))
        directors = Counter(min(len({c["id"] for c in crew if c["job"] == "Director"}), 3) for crew in crews)
        director_acts = sum(1 for cast, crew in zip(casts, crews)
                            if {c["id"] for c in crew if c["job"] == "Director"} & {c["id"] for c in cast})
        print()
        table([["Cast order %s" % k, f"{v:,}"] for k, v in orders.most_common()] +
              [["Movies where an actor has more than one role", f"{repeated:,}"],
               ["Movies without a Director in the crew", f"{directors[0]:,}"],
               ["Movies with 1 / 2 / 3+ directors", "%s / %s / %s" % tuple(f"{directors[k]:,}" for k in (1, 2, 3))],
               ["Movies where a director is also in the cast", f"{director_acts:,}"]])

        ids_per_name = defaultdict(set)
        for cast in casts:
            for c in cast:
                ids_per_name[c["name"]].add(c["id"])
        shared = sorted(((name, ids) for name, ids in ids_per_name.items() if len(ids) > 1), key=lambda x: -len(x[1]))
        pairs = sum(len({c["id"] for c in cast}) * (len({c["id"] for c in cast}) - 1) // 2 for cast in casts)
        print()
        table([["Distinct actors (person ids)", f"{len({c['id'] for cast in casts for c in cast}):,}"],
               ["Distinct actor names", f"{len(ids_per_name):,}"],
               ["Names used by more than one person id", f"{len(shared):,}"],
               ["Examples", ", ".join("%s (%d ids)" % (name, len(ids)) for name, ids in shared[:3])],
               ["Distinct actor pairs per movie, summed", f"{pairs:,}"]])
        print("-> People are identified by their TMDB person id, the name is only used for display.")

    def keywords_file(self):
        heading("14. keywords.csv")
        groups = defaultdict(list)
        with open(cleaning.KEYWORDS_CSV, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            for movie_id, words in reader:
                groups[int(movie_id)].append(words)
        keywords = cleaning.read_keywords()
        per_movie = sorted(len(keywords.get(m, [])) for m in self.movies)
        counts = Counter(k for m in self.movies for k in keywords.get(m, []))
        noir = {m for m in self.movies if {"film noir", "neo-noir"} & set(keywords.get(m, []))}
        noir_in_text = sum(1 for m in noir if "noir" in ((self.movies[m]["overview"] or "") + " " +
                                                         (self.movies[m]["tagline"] or "")).lower())
        table([["Rows", f"{sum(len(g) for g in groups.values()):,}"],
               ["Unique movie ids", f"{len(groups):,}"],
               ["Extra (duplicate) rows", sum(len(g) - 1 for g in groups.values())],
               ["Duplicate groups that are not exact copies", sum(1 for g in groups.values() if len(set(g)) > 1)],
               ["Keyword rows for ids not in movies_metadata", len(set(groups) - set(self.movies))],
               ["Movies without keywords (empty list or no row)", f"{per_movie.count(0):,}"],
               ["Keywords per movie: median / max", "%d / %d" % (percentile(per_movie, 50), per_movie[-1])],
               ["Distinct keywords", f"{len(counts):,}"],
               ["Movies with keyword 'film noir' or 'neo-noir'", len(noir)],
               ["Noir keyword and 'noir' in overview or tagline", noir_in_text]])
        print("\nMost common keywords: " + ", ".join("%s (%s)" % (k, f"{c:,}") for k, c in counts.most_common(8)))

    def links_file(self):
        heading("15. links.csv / links_small.csv")
        rows = []
        for name in ("links.csv", "links_small.csv"):
            links = cleaning.read_links(os.path.join(cleaning.DATA_DIR, name))
            per_tmdb = Counter(t for t in links.values() if t is not None)
            rows.append([name, f"{len(links):,}", sum(1 for t in links.values() if t is None),
                         sum(1 for t in links.values() if t is not None and t not in self.movies),
                         sum(1 for c in per_tmdb.values() if c > 1)])
        table(rows, ["File", "MovieLens ids", "Empty tmdbId", "tmdbId not in movies", "tmdbIds with > 1 MovieLens id"])
        small = cleaning.read_links(os.path.join(cleaning.DATA_DIR, "links_small.csv"))
        full = cleaning.read_links()
        print("MovieLens ids in links_small.csv but not in links.csv: %d. Ids in both with a different tmdbId: %d."
              % (sum(1 for k in small if k not in full), sum(1 for k, v in small.items() if k in full and full[k] != v)))

    def ratings_file(self):
        heading("16. ratings.csv (the full file with 26 million ratings)")
        links = cleaning.read_links()
        per_movie = Counter()
        mapping = Counter()
        tmdb_seen = set()
        current_user = None
        first = last = None
        for user_id, movielens_id, rating, timestamp in cleaning.read_ratings():
            if user_id != current_user:
                current_user, tmdb_seen = user_id, set()
            self.ratings_per_user[user_id] += 1
            self.rating_values[rating] += 1
            per_movie[movielens_id] += 1
            first = timestamp if first is None else min(first, timestamp)
            last = timestamp if last is None else max(last, timestamp)
            tmdb_id = links.get(movielens_id, "no link")
            if tmdb_id == "no link":
                mapping["MovieLens id not in links.csv"] += 1
            elif tmdb_id is None:
                mapping["Movie has no tmdbId"] += 1
            elif tmdb_id not in self.movies:
                mapping["tmdbId not in movies_metadata"] += 1
            else:
                mapping["Linked to a movie"] += 1
                if tmdb_id in tmdb_seen:
                    mapping["(Linked) same user and TMDB movie as an earlier rating"] += 1
                tmdb_seen.add(tmdb_id)
        n = sum(self.ratings_per_user.values())
        users = sorted(self.ratings_per_user.values())
        movies = sorted(per_movie.values())
        table([["Ratings", f"{n:,}"],
               ["Users", f"{len(users):,}"],
               ["Rated MovieLens movies", f"{len(movies):,}"],
               ["First / last rating (UTC)",
                "%s / %s" % (cleaning.parse_timestamp(first), cleaning.parse_timestamp(last))],
               ["Ratings per user: min / median / mean / max",
                "%d / %d / %.1f / %s" % (users[0], percentile(users, 50), n / len(users), f"{users[-1]:,}")],
               ["Users with >= 20 ratings", f"{sum(1 for u in users if u >= 20):,}"],
               ["Users with 1 rating", f"{users.count(1):,}"],
               ["Ratings per movie: median / max", "%d / %s" % (percentile(movies, 50), f"{movies[-1]:,}")]])
        print()
        table([[v, f"{c:,}", "%.1f %%" % pct(c, n)] for v, c in sorted(self.rating_values.items())],
              ["Rating", "Ratings", "Share"])
        print()
        table([[k, f"{c:,}", "%.2f %%" % pct(c, n)] for k, c in mapping.items()], ["Link to movies", "Ratings", "Share"])
        print("(The data is sorted by user, so the same user rating one TMDB movie twice is found per user.)")

        small_users, small_movies, small_n = set(), set(), 0
        for user_id, movielens_id, _, _ in cleaning.read_ratings(os.path.join(cleaning.DATA_DIR, "ratings_small.csv")):
            small_n += 1
            small_users.add(user_id)
            small_movies.add(movielens_id)
        print("\nratings_small.csv for comparison: %s ratings, %d users, %s movies (not used)."
              % (f"{small_n:,}", len(small_users), f"{len(small_movies):,}"))

    # ------------------------------------------------------------------ #
    def figures(self):
        os.makedirs(FIGURE_DIR, exist_ok=True)
        plt.rcParams.update({
            "font.family": "sans-serif", "font.size": 10, "axes.edgecolor": MUTED,
            "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
            "axes.titlecolor": INK, "axes.titlesize": 11, "axes.titleweight": "bold",
            "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
            "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
            "legend.frameon": False, "savefig.dpi": 160, "savefig.bbox": "tight",
        })
        movies = list(self.movies.values())
        n = len(movies)

        # Share of movies where an attribute is unknown after cleaning
        def directors(m):
            return [c for c in self.credits.get(m["_id"], ([], []))[1] if c["job"] == "Director"]
        checks = [("revenue", lambda m: m["revenue"] is None), ("budget", lambda m: m["budget"] is None),
                  ("belongs_to_collection", lambda m: m["belongs_to_collection"] is None),
                  ("tagline", lambda m: m["tagline"] is None),
                  ("production_companies", lambda m: not m["production_companies"]),
                  ("production_countries", lambda m: not m["production_countries"]),
                  ("cast", lambda m: not self.credits.get(m["_id"], ([], []))[0]),
                  ("vote_average", lambda m: m["vote_average"] is None),
                  ("genres", lambda m: not m["genres"]),
                  ("overview", lambda m: m["overview"] is None),
                  ("director (crew)", lambda m: not directors(m)),
                  ("runtime", lambda m: m["runtime"] is None),
                  ("release_date", lambda m: m["release_date"] is None)]
        shares = sorted(((name, pct(sum(1 for m in movies if missing(m)), n)) for name, missing in checks),
                        key=lambda s: -s[1])
        fig, ax = plt.subplots(figsize=(8, 4.2))
        ax.barh([s[0] for s in shares][::-1], [s[1] for s in shares][::-1], color=BLUE, height=0.65)
        for i, (_, share) in enumerate(shares[::-1]):
            ax.text(share + 0.8, i, "%.1f %%" % share, va="center", fontsize=8.5, color=INK_2)
        ax.set_xlim(0, 100)
        ax.set_xlabel("Share of the %s movies (%%)" % f"{n:,}")
        ax.set_title("Unknown values per attribute after cleaning")
        ax.grid(axis="y", visible=False)
        fig.savefig(os.path.join(FIGURE_DIR, "eda_missing_values.png"))
        plt.close(fig)

        # Movies per release decade
        decades = sorted(self.decades)
        fig, ax = plt.subplots(figsize=(9, 3.2))
        ax.bar(range(len(decades)), [self.decades[d] for d in decades], width=0.7, color=BLUE)
        ax.set_xticks(range(len(decades)))
        ax.set_xticklabels(["%ds" % d for d in decades], rotation=45, ha="right")
        ax.set_ylabel("Movies")
        ax.set_title("Movies per release decade")
        ax.yaxis.set_major_formatter(THOUSANDS)
        ax.grid(axis="x", visible=False)
        fig.savefig(os.path.join(FIGURE_DIR, "eda_release_decades.png"))
        plt.close(fig)

        # Genres: all genres and first genre
        any_genre = Counter(g for m in movies for g in m["genres"])
        first_genre = Counter(m["genres"][0] for m in movies if m["genres"])
        names = [g for g, _ in any_genre.most_common()]
        fig, ax = plt.subplots(figsize=(9, 3.6))
        xs = range(len(names))
        ax.bar([x - 0.2 for x in xs], [any_genre[g] for g in names], width=0.4, color=BLUE, label="Any genre")
        ax.bar([x + 0.2 for x in xs], [first_genre[g] for g in names], width=0.4, color=ORANGE,
               label="First genre (task 5)")
        ax.set_xticks(list(xs))
        ax.set_xticklabels(names, rotation=45, ha="right")
        ax.set_ylabel("Movies")
        ax.set_title("Movies per genre")
        ax.yaxis.set_major_formatter(THOUSANDS)
        ax.grid(axis="x", visible=False)
        ax.legend()
        fig.savefig(os.path.join(FIGURE_DIR, "eda_genres.png"))
        plt.close(fig)

        # Runtime and vote_average
        fig, axes = plt.subplots(1, 2, figsize=(9, 3.2))
        axes[0].hist([m["runtime"] for m in movies if m["runtime"] and m["runtime"] <= 240], bins=48,
                     color=BLUE, rwidth=0.85)
        axes[0].set_xlabel("Runtime (min, movies <= 240 min shown)")
        axes[0].set_ylabel("Movies")
        axes[0].set_title("Runtime")
        bins = [x / 2 + 0.25 for x in range(0, 21)]
        axes[1].hist([m["vote_average"] for m in movies if m["vote_average"] is not None], bins=bins,
                     color=BLUE, rwidth=0.85, label="all with votes")
        axes[1].hist([m["vote_average"] for m in movies if m["vote_average"] is not None and m["vote_count"] >= 50],
                     bins=bins, color=ORANGE, rwidth=0.85, label="vote_count >= 50")
        axes[1].set_xlabel("vote_average")
        axes[1].set_title("vote_average")
        axes[1].legend(loc="upper left")
        for ax in axes:
            ax.yaxis.set_major_formatter(THOUSANDS)
            ax.grid(axis="x", visible=False)
        fig.tight_layout()
        fig.savefig(os.path.join(FIGURE_DIR, "eda_runtime_votes.png"))
        plt.close(fig)

        # Budget against revenue, raw values > 0
        points = [(number(r, "budget"), number(r, "revenue")) for r in self.raw.values()
                  if number(r, "budget") > 0 and number(r, "revenue") > 0]
        tiny = [(b, r) for b, r in points if b < cleaning.MIN_MONEY_USD or r < cleaning.MIN_MONEY_USD]
        fine = [(b, r) for b, r in points if b >= cleaning.MIN_MONEY_USD and r >= cleaning.MIN_MONEY_USD]
        fig, ax = plt.subplots(figsize=(6.5, 5))
        ax.scatter([b for b, _ in fine], [r for _, r in fine], s=4, color=BLUE, alpha=0.4, linewidths=0,
                   label="kept (%s movies)" % f"{len(fine):,}")
        ax.scatter([b for b, _ in tiny], [r for _, r in tiny], s=10, color=ORANGE, linewidths=0,
                   label="budget or revenue < %s USD (%d)" % (f"{cleaning.MIN_MONEY_USD:,}", len(tiny)))
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Budget (USD, log scale)")
        ax.set_ylabel("Revenue (USD, log scale)")
        ax.set_title("Budget and revenue (movies where both are > 0)")
        ax.legend(loc="upper left")
        fig.savefig(os.path.join(FIGURE_DIR, "eda_budget_revenue.png"))
        plt.close(fig)

        # Gender of the cast by billing position
        fig, ax = plt.subplots(figsize=(9, 3.2))
        positions = sorted(self.gender_by_position)
        bottom = [0.0] * len(positions)
        for gender, color, label in [("female", ORANGE, "female"), ("male", BLUE, "male"), (None, GRID, "unknown")]:
            shares = [pct(self.gender_by_position[p][gender], sum(self.gender_by_position[p].values()))
                      for p in positions]
            ax.bar(positions, shares, bottom=bottom, width=0.7, color=color, label=label)
            bottom = [b + s for b, s in zip(bottom, shares)]
        ax.set_xticks(positions)
        ax.set_xticklabels([str(p + 1) for p in positions])
        ax.set_xlabel("Billing position (1 = top-billed)")
        ax.set_ylabel("Share of cast entries (%)")
        ax.set_title("Gender of the cast by billing position")
        ax.set_ylim(0, 100)
        ax.grid(axis="x", visible=False)
        ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.22))
        fig.savefig(os.path.join(FIGURE_DIR, "eda_cast_gender.png"))
        plt.close(fig)

        # Ratings: values and ratings per user
        fig, axes = plt.subplots(1, 2, figsize=(9, 3.2))
        values = sorted(self.rating_values)
        axes[0].bar(values, [self.rating_values[v] / 1e6 for v in values], width=0.4, color=BLUE)
        axes[0].set_xticks(values)
        axes[0].set_xticklabels([("%g" % v) for v in values], fontsize=8)
        axes[0].set_xlabel("Rating")
        axes[0].set_ylabel("Ratings (millions)")
        axes[0].set_title("Rating values")
        edges = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 20000]
        counts = [sum(1 for c in self.ratings_per_user.values() if lo <= c < hi) for lo, hi in zip(edges, edges[1:])]
        axes[1].bar(range(len(counts)), counts, width=0.7,
                    color=[ORANGE if hi <= 20 else BLUE for hi in edges[1:]])
        axes[1].set_xticks(range(len(counts)))
        axes[1].set_xticklabels(["%d-%d" % (lo, hi - 1) if hi - lo > 1 else str(lo) for lo, hi in zip(edges, edges[1:])],
                                rotation=45, ha="right", fontsize=8)
        axes[1].set_xlabel("Ratings per user (orange: < 20)")
        axes[1].set_ylabel("Users")
        axes[1].set_title("Ratings per user")
        axes[1].yaxis.set_major_formatter(THOUSANDS)
        for ax in axes:
            ax.grid(axis="x", visible=False)
        fig.tight_layout()
        fig.savefig(os.path.join(FIGURE_DIR, "eda_ratings.png"))
        plt.close(fig)
        print("\nFigures written to report/figures/")


def main():
    EDA().run()


if __name__ == "__main__":
    main()
