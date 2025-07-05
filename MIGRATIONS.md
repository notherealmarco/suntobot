# Database Migrations Guide

This project uses **Alembic** for database migrations. This ensures that when you modify your database models, the changes are properly applied to the database.

With Alembic migrations, you can safely evolve your database schema over time.

## Setup

1. **Install dependencies** (already done):
   ```bash
   uv sync
   ```

2. **Set your DATABASE_URL** in `.env` file:
   ```
   DATABASE_URL=postgresql://username:password@localhost/dbname
   ```

## Common Migration Commands

### 1. Create a New Migration
When you modify your models in `src/database.py`, create a migration:

```bash
python run_migration.py revision --autogenerate -m "Add new column to messages table"
```

This will:
- Compare your models with the current database schema
- Generate a migration file in `alembic/versions/`
- You should review the generated migration before running it

### 2. Apply Migrations
To apply pending migrations to your database:

```bash
python run_migration.py upgrade head
```

### 3. Check Migration Status
To see current migration status:

```bash
python run_migration.py current
```

To see migration history:

```bash
python run_migration.py history
```

### 4. Rollback Migrations
To rollback one migration:

```bash
python run_migration.py downgrade -1
```

To rollback to a specific migration:

```bash
python run_migration.py downgrade <revision_id>
```

## Typical Workflow

1. **Modify your models** in `src/database.py`
2. **Generate migration**: `python run_migration.py revision --autogenerate -m "Description of changes"`
3. **Review the generated migration** in `alembic/versions/`
4. **Apply migration**: `python run_migration.py upgrade head`
5. **Start your bot** - the database will be up to date!

## Initial Setup for Existing Database

If you have an existing database, you need to create an initial migration:

```bash
python run_migration.py revision --autogenerate -m "Initial migration"
python run_migration.py upgrade head
```

## Examples

### Adding a new column to Message table:

1. Edit `src/database.py`:
   ```python
   class Message(Base):
       # ...existing columns...
       new_field = Column(String(255))  # Add this line
   ```

2. Generate migration:
   ```bash
   python run_migration.py revision --autogenerate -m "Add new_field to messages"
   ```

3. Apply migration:
   ```bash
   python run_migration.py upgrade head
   ```

### Creating a new table:

1. Add new model in `src/database.py`:
   ```python
   class NewTable(Base):
       __tablename__ = "new_table"
       id = Column(Integer, primary_key=True)
       name = Column(String(255))
   ```

2. Generate and apply migration:
   ```bash
   python run_migration.py revision --autogenerate -m "Add new_table"
   python run_migration.py upgrade head
   ```

## Troubleshooting

- **"Can't load plugin" error**: Make sure DATABASE_URL is correctly set
- **Import errors**: Ensure your models are properly imported in `alembic/env.py`
- **Database connection issues**: Check your DATABASE_URL format and database server

## Advanced Usage

You can also use the native alembic commands directly:

```bash
uv run alembic revision --autogenerate -m "migration message"
uv run alembic upgrade head
uv run alembic downgrade -1
```

The `run_migration.py` script is just a convenience wrapper that handles environment setup.
