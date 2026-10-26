# TDT4225 Assignment 3 – The Movies Dataset in MongoDB

## Folder structure

| Path | Content |
|---|---|
| `src/DbConnector.py` | MongoDB connection (settings from environment variables) |
| `src/cleaning.py` | Shared parsing and cleaning rules (used by both EDA and insert) |
| `src/part1_eda.py` | Part 1.1 – exploratory data analysis, writes figures to `report/figures/` |
| `src/part1_insert.py` | Part 1.2 – collections with validators, insertion of the cleaned data and indexes |
| `src/part2_queries.py` | Part 2 – one method per task (aggregation pipelines + Python) |
| `src/requirements.txt` | pip packages |
| `output/` | Console output of the programs, and CSV files with the full answers of tasks 2, 5 and 10 |
| `report/figures` | The EDA figures |
| `data/` | The dataset CSV files from Kaggle (not included in Git) |

## Setup

1. Start MongoDB 7.0.1 in its own Docker container, with an admin user:

   ```bash
   docker run --name tdt4225-a3-mongo -e MONGO_INITDB_ROOT_USERNAME=admin -e MONGO_INITDB_ROOT_PASSWORD=<root-password> -p 27017:27017 -d mongo:7.0.1 --wiredTigerCacheSizeGB 4
   ```

2. Create the database user with read/write access to `movies_db` (step 8 of
   the database setup in the assignment):

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
```
