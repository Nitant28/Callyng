import re

with open("db/postgres.py", "r") as f:
    content = f.read()

# Replace the create_db_pool function
new_func = """async def create_db_pool(dsn: str) -> asyncpg.Pool:
    \"\"\"Creates an asyncpg connection pool.\"\"\"
    import os
    min_size = int(os.getenv("DB_POOL_MIN", "5"))
    max_size = int(os.getenv("DB_POOL_MAX", "50"))
    
    pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=min_size,
        max_size=max_size,
        command_timeout=30,
        init=_init_connection,
    )
    return pool
"""

content = re.sub(r'async def create_db_pool\(dsn: str\) -> asyncpg\.Pool:.*?return _pool\n', new_func, content, flags=re.DOTALL)

with open("db/postgres.py", "w") as f:
    f.write(content)
