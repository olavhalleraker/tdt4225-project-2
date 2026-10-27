# TDT4225 Assignment 3 – The Movies Dataset in MongoDB

## Folder structure

| Path | Content |
|---|---|
| `src/DbConnector.py` | MongoDB connection (settings from environment variables) |
| `src/cleaning.py` | Shared parsing and cleaning rules (used by both EDA and insert) |
| `src/part1_eda.py` | Part 1.1 – exploratory data analysis, writes figures to `report/figures/` |
| `src/part1_insert.py` | Part 1.2 – collections with validators, insertion of the cleaned data and indexes |
| `src/part2_queries.py` | Part 2 – one method per task (aggregation pipelines + Python) |
| `src/explain_indexes.py` | `explain()` of some queries: which use an index and which scan the collection, plus index sizes |
| `src/requirements.txt` | pip packages |
| `output/` | Console output of the programs, and CSV files with the full answers of tasks 2, 5 and 10 |
| `report/figures` | The EDA figures |
| `data/` | The dataset CSV files from Kaggle (not included in Git) |

## Setup

1. Start MongoDB 7.0.1 in its own Docker container, with an admin user:

   ```bash
   docker run --name tdt4225-a3-mongo -e MONGO_INITDB_ROOT_USERNAME=admin -e MONGO_INITDB_ROOT_PASSWORD=<root-password> -p 27017:27017 -d mongo:7.0.1 --wiredTigerCacheSizeGB 4
   ```

2. Create the database user with read/write access to `movies_db`:

   ```bash
   docker exec tdt4225-a3-mongo mongosh -u admin -p <root-password> --authenticationDatabase admin --eval "db.getSiblingDB('movies_db').createUser({user: 'tdt4225', pwd: '<password>', roles: ['readWrite']})"
   ```

3. Install the Python packages:

   ```bash
   python3.11 -m venv .venv && .venv/bin/pip install -r src/requirements.txt
   ```

4. Download The Movies Dataset from Kaggle (`rounakbanik/the-movies-dataset`)
   and extract the CSV files to `data/` (`movies_metadata.csv`, `credits.csv`,
   `keywords.csv`, `links.csv`, `ratings.csv`, plus the small versions).

5. Give the programs the database password (and optionally `DB_HOST`,
   `DB_PORT`, `DB_NAME`, `DB_USER`; defaults: localhost, 27017, movies_db, tdt4225):

   ```bash
   export DB_PASSWORD=<password>
   ```

## Run (from `src/`)

```bash
python part1_eda.py | tee ../output/part1_eda.txt
python part1_insert.py | tee ../output/part1_insert.txt
python part2_queries.py | tee ../output/part2_results.txt
python explain_indexes.py | tee ../output/explain_indexes.txt
```

## Design decisions (short version, see the report for the discussion)

- **Two collections.** `movies` has one document per movie, with `_id` = the TMDB
  id. Cast, crew, keywords and the MovieLens ids are embedded, because they belong
  to one movie, are read together with it (tasks 1–9 need no join) and are bounded
  in size (at most a few hundred entries, about 3.3 KB per document on average,
  far below the 16 MB limit). `ratings` is a separate collection with one document
  per rating and a one-way reference `movie_id` → `movies._id`, because a movie
  can have tens of thousands of ratings (26 million in total), which cannot be
  embedded.
- **Duplicated people data.** Actors and directors are many-to-many with movies.
  Their id and name are copied into every movie they appear in. This is fine for
  a read-only dataset, but would give update anomalies if names changed. People
  are always grouped by their TMDB person id, since names are not unique.
- **Missing values** are stored as `null` (or `[]` for lists), never as 0 or
  `""`, so that aggregations do not count them (budget/revenue 0 or below 1,000
  USD, runtime 0, vote_average 0, placeholder overviews, gender code 0).
- **Types and dates.** Integers are stored as int/long, ratings as double and all
  dates as BSON dates in UTC (`release_date` at 00:00, `rated_at` from the Unix
  timestamp), so dates are consistent across both collections.
- **Schema validation.** Both collections have a `$jsonSchema` validator, so the
  document structure is checked when data is written (schema-on-write).
- **Indexes.** A text index on `overview` + `tagline` (task 7) and a unique
  index on `(user_id, movielens_id)` in `ratings`. They are created after the
  bulk insert, which is faster than updating them for every insert. The other
  tasks scan the whole `movies` collection (about 150 MB), so more indexes would
  not help them. `explain_indexes.py` shows this.
- **Bulk insert.** Ratings are streamed from the CSV file and inserted in batches
  of 50,000 with `ordered=False` (about 2.6 minutes for 26 million ratings).
