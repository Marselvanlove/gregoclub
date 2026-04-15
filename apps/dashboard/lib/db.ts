import { DatabaseSync } from "node:sqlite";

import { neon } from "@neondatabase/serverless";

export type DatabaseKind = "none" | "postgres" | "sqlite";

function readDatabaseUrl() {
  return process.env.DATABASE_URL?.trim() ?? "";
}

export function hasDatabaseUrl() {
  return readDatabaseUrl().length > 0;
}

export function getDatabaseKind(): DatabaseKind {
  const databaseUrl = readDatabaseUrl();
  if (!databaseUrl) return "none";
  if (databaseUrl.startsWith("sqlite")) return "sqlite";
  if (databaseUrl.startsWith("postgres")) return "postgres";
  return "none";
}

function normalizePostgresUrl(databaseUrl: string) {
  return databaseUrl
    .replace(/^postgresql\+asyncpg:\/\//, "postgresql://")
    .replace(/^postgres\+asyncpg:\/\//, "postgres://")
    .replace(/^postgresql\+psycopg:\/\//, "postgresql://")
    .replace(/^postgres\+psycopg:\/\//, "postgres://");
}

function getPostgresClient() {
  const databaseUrl = readDatabaseUrl();
  if (!databaseUrl) {
    throw new Error("DATABASE_URL is required for the dashboard");
  }

  return neon(normalizePostgresUrl(databaseUrl));
}

function extractSqlitePath(databaseUrl: string) {
  // Keep SQLite path resolution deterministic so Next.js NFT doesn't trace the whole repo.
  return databaseUrl.replace(/^sqlite(?:\+aiosqlite)?:\/\/\//, "");
}

const sqliteConnections = new Map<string, DatabaseSync>();

function getSqliteClient() {
  const databaseUrl = readDatabaseUrl();
  if (!databaseUrl) {
    throw new Error("DATABASE_URL is required for the dashboard");
  }

  const sqlitePath = extractSqlitePath(databaseUrl);
  let client = sqliteConnections.get(sqlitePath);

  if (!client) {
    client = new DatabaseSync(sqlitePath);
    sqliteConnections.set(sqlitePath, client);
  }

  return client;
}

export async function query<T>(statement: string, params: unknown[] = []): Promise<T[]> {
  const sql = getPostgresClient();
  return (await sql(statement, params)) as T[];
}

export function readSqliteRows<T>(statement: string, params?: Record<string, unknown> | unknown[]): T[] {
  const client = getSqliteClient();
  const preparedStatement = client.prepare(statement);

  if (Array.isArray(params)) {
    return preparedStatement.all(...(params as any[])) as T[];
  }

  if (params) {
    return preparedStatement.all(params as Record<string, any>) as T[];
  }

  return preparedStatement.all() as T[];
}
