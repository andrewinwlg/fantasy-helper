# Fantasy Helper

## To run from scratch

First you will need to `pip install` `pandas`, `lxml3`, `sqlite`, and if you have an old version of `pandas`, then: `pip install --upgrade pandas`

```bash
python nba_scraper.py
python post_scraper.py
python calc_fpts.py
```

Note that nba_scraper.py takes a long time to run, maybe up to an hour?

This will create the SQLite database with tables and views.

## To update with new data

To fetch only new games since the last update:

```bash
python incremental_update.py
```

## To view the data

You can download any SQLite viewer like [DB Browser for SQLite](https://sqlitebrowser.org/dl/) and use that to view the data in a graphical layout, export to excel, etc.

## TODOs for this project

- [x] An incremental data fetcher that only gets new data since the last time it was run
- [ ] Present the data in a webpage
- [ ] Do some basic data science to evaluate who are valuable players
- [ ] Load your own fantasy team into the database for analysis
- [ ] Load your whole fantasy league into the database for analysis
- [ ] Secure storage of fantasy league credentials
- [ ] Build an AI agent that can translate English language requests into recommendations, e.g. "who should I consider trading with?" "what free agent shows the most promise?" etc
- [ ] Make the whole thing multi-tenant so different users can login and see only their own fantasy league/team
- [ ] Package the whole thing up in deployable containers
- [ ] Web interface for some simple use-cases
