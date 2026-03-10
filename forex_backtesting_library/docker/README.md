# ClickHouse for forex_backtesting_library

Starts ClickHouse with **user `root`**, **database `default`**, and a password from `.env`.

## Setup

```bash
cd docker
cp .env.example .env
# Edit .env if you want a different CLICKHOUSE_PASSWORD
docker compose up -d
```

## Connect

- **Host:** localhost  
- **Port:** 8123 (HTTP) / 9000 (native)  
- **User:** root  
- **Database:** default  
- **Password:** value of `CLICKHOUSE_PASSWORD` in `.env`

For the app or `setup_database.py`:

```bash
export CLICKHOUSE_HOST=localhost
export CLICKHOUSE_PORT=8123
export CLICKHOUSE_USERNAME=root
export CLICKHOUSE_PASSWORD=<same as in .env>
export CLICKHOUSE_DATABASE=default
```

Then run `scripts/setup_database.py` from the project root to create the `vectorbt_grid` database and user.
