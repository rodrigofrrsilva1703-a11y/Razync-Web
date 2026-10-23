"""One-way removal of storage belonging to the discontinued A1 feature."""
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger('uvicorn.error')


def remove_retired_credentials(database_path):
    """Erase retired rows in the local database and its pre-migration backups.

    Keep the business tables and migration markers. Never decrypt or log data.
    Run before migration so new backups cannot include the retired storage.
    """
    path = Path(database_path)
    candidates = [path, *sorted(path.parent.glob(path.stem + '.pre-supabase-*.sqlite3'))]
    removed = 0
    cleaned = 0
    for candidate in candidates:
        if not candidate.is_file() or candidate.is_symlink():
            continue
        # mode=rw prevents accidentally creating a database during cleanup.
        con = sqlite3.connect(candidate.resolve().as_uri() + '?mode=rw', uri=True, timeout=30)
        try:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='certificates'").fetchone():
                continue
            count = con.execute('SELECT COUNT(*) FROM certificates').fetchone()[0]
            con.execute('PRAGMA secure_delete=ON')
            con.execute('DROP TABLE certificates')
            con.commit()
            con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            con.execute('VACUUM')
            con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='certificates'").fetchone():
                raise RuntimeError('Não foi possível remover os dados descontinuados.')
            removed += count
            cleaned += 1
        finally:
            con.close()
    logger.info('Retired A1 storage removed: databases=%d, records=%d, remaining_tables=0', cleaned, removed)
    return {'databases': cleaned, 'records': removed}
