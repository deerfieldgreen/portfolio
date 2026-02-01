-- Create app user and database for news_agent.
-- Run via init_clickhouse.sh which substitutes ${CLICKHOUSE_PASSWORD} from env (no secrets in file).
-- Requires default user (e.g. clickhouse-client without password for local Docker).

CREATE USER IF NOT EXISTS news_agent
  IDENTIFIED WITH sha256_password BY '${CLICKHOUSE_PASSWORD}'
  HOST ANY;

CREATE DATABASE IF NOT EXISTS news_agent;

GRANT ALL ON news_agent.* TO news_agent;
