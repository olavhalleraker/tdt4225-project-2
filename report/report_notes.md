# Notes for the report (Part 3)

Checklist and points to cover. The report itself (PDF, report template from
exercise 2) is not in the repository.

## Checklist

- [ ] Group number and members on the front page
- [ ] Part 1: EDA findings with screenshots (`output/part1_eda.txt`) and the
      figures in `report/figures/`, including section 17 (impact of missing values)
- [ ] Part 1: database design and why (see "Design decisions" in `README.md`)
- [ ] Part 2: a screenshot of the result of every task (`output/part2_results.txt`),
      plus 2 to 4 lines per task on interpretation and caveats (below).
      Tasks 2, 5 and 10 have the full answer in CSV files in `output/`
- [ ] Index use: screenshot of `output/explain_indexes.txt`
- [ ] How AI was used (required by NTNU)
- [ ] Hand in the PDF and the code (without `data/`) by Oct 30, 14:00

## Interpretation choices to state per task

1. Main answer uses directors with >= 5 movies with known revenue. The literal
   reading (>= 5 movies, median over the known revenues) is printed as well.
   Movie count and mean vote_average are over all of the director's movies.
2. Pairs are counted by person id. Only the top 30 of all pairs are printed,
   the full list is in `output/task2_actor_pairs.csv`. Ties are ordered by the
   average vote_average.
3. Many actors are tied at the maximum number of genres, so the top 10 is
   decided by the tie-breaker (fewer credited movies first). The example genres
   are the actor's 5 most common genres.
4. total_revenue only sums known revenues, so it is a lower bound when
   movies_with_revenue < movies.
5. Sorted by decade ascending, then median runtime descending. Movies with
   unknown runtime are counted but not used for the median. Groups with very
   few movies (before 1910) give unreliable medians.
6. Top 5 by billing order first, then unknown gender is ignored. The value is
   the mean of the per-movie proportions. Decades with 1 or 2 movies are noise.
7. The text index splits "neo-noir" into "neo" and "noir", so searching "noir"
   finds both. Searching for "noir neo-noir" would also match every overview
   with "Neo" (e.g. The Matrix). Fewer than 20 movies are returned because few
   overviews or taglines use the word (checked with a regex).
8. A director acting in their own film is not counted as a pair. These
   self-pairs are listed separately. mean_revenue is over the known revenues.
9. Companies have no country in the data, so only the company name can be
   checked. "xx" is TMDB's code for no language.
10. The >= 20 ratings filter is applied to both lists. Many users have rated
    all genres, so the top 10 is decided by the tie-breaker (fewer ratings
    first). Unlinked ratings count in ratings and variance, not in genres.

## Links to the curriculum

- Document vs relational model, embedding and locality, one-to-many vs
  many-to-many, joins with `$lookup` (task 10): DDIA chapter on data models
  (`chap3`), Stonebraker/Pavlo and "What goes around comes around"
- Schema-on-read vs schema-on-write (`$jsonSchema` validators): `chap3`
- Indexes: B-trees in WiredTiger vs LSM-trees, text (inverted) index, compound
  index and the left-prefix rule, build indexes after bulk load: `chap4`, `lsm`
- Encoding: CSV/JSON ambiguity, BSON repeats field names in every document
  (ratings: about 100 bytes per document): `chap5`
- Aggregation pipeline vs MapReduce (`$unwind` ~ map, `$group` ~ shuffle and
  reduce, `allowDiskUse` ~ spill to disk): Stonebraker/Pavlo
- `$out` in task 10 is a materialized view (derived data): `chap1`, `chap4`
- How it would scale: shard `ratings` on a hashed `user_id` (task 10 groups per
  user), keep `movies` unsharded, replica set for reads: `chap6`, `chap7`
- Timestamps stored in UTC: "Time and global states" / Coulouris chapter 14
