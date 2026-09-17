DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'films' AND column_name = 'themes'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'films' AND column_name = 'lenses'
  ) THEN
    ALTER TABLE films RENAME COLUMN themes TO lenses;
  END IF;
END $$;

DROP INDEX IF EXISTS idx_films_themes;
CREATE INDEX IF NOT EXISTS idx_films_lenses ON films USING GIN (lenses);
