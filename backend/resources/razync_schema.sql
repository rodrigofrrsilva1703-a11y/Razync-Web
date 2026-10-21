-- Private schema: no data is exposed through the browser Data API.
CREATE SCHEMA IF NOT EXISTS razync;
REVOKE ALL ON SCHEMA razync FROM PUBLIC, anon, authenticated;
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'razync_api') THEN
    CREATE ROLE razync_api NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS CONNECTION LIMIT 5;
  END IF;
END $$;
GRANT USAGE ON SCHEMA razync TO razync_api;
CREATE TABLE IF NOT EXISTS razync.classification_records (
 company INTEGER NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(company,id));
CREATE TABLE IF NOT EXISTS razync.classification_imports (
 company INTEGER NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(company,digest));
CREATE TABLE IF NOT EXISTS razync.patterns (
 company INTEGER NOT NULL, bank TEXT NOT NULL, signature TEXT NOT NULL,
 nature TEXT NOT NULL, counterpart TEXT NOT NULL, period TEXT NOT NULL,
 example TEXT, occurrences INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(company,bank,signature,nature,counterpart,period));
CREATE TABLE IF NOT EXISTS razync.manual_tasks (
 id TEXT PRIMARY KEY, titulo TEXT NOT NULL, descricao TEXT, codigo_empresa TEXT,
 categoria TEXT, prioridade TEXT, prazo TEXT, status TEXT NOT NULL DEFAULT 'Pendente',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS razync.company_task_status (
 codigo_empresa TEXT NOT NULL, competencia TEXT NOT NULL, concluida INTEGER NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL, PRIMARY KEY(codigo_empresa,competencia));
CREATE TABLE IF NOT EXISTS razync.custom_companies (
 codigo INTEGER PRIMARY KEY, nome TEXT NOT NULL, regime TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS razync.migration_state (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), migration_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL, created_at TEXT NOT NULL);
DO $$ DECLARE t TEXT; BEGIN
  FOREACH t IN ARRAY ARRAY['classification_records','classification_imports','patterns',
    'manual_tasks','company_task_status','custom_companies','migration_state'] LOOP
    EXECUTE format('ALTER TABLE razync.%I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('REVOKE ALL ON TABLE razync.%I FROM PUBLIC,anon,authenticated',t);
    EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE razync.%I TO razync_api',t);
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='razync' AND tablename=t AND policyname='server_only') THEN
      EXECUTE format('CREATE POLICY server_only ON razync.%I TO razync_api USING (true) WITH CHECK (true)',t);
    END IF;
  END LOOP;
END $$;
