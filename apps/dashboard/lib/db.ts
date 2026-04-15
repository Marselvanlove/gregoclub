import { neon } from "@neondatabase/serverless";

function getSqlClient() {
  const databaseUrl = process.env.DATABASE_URL;
  if (!databaseUrl) {
    throw new Error("DATABASE_URL is required for the dashboard");
  }
  return neon(databaseUrl);
}

export async function query<T>(statement: string, params: unknown[] = []): Promise<T[]> {
  const sql = getSqlClient();
  return (await sql(statement, params)) as T[];
}
