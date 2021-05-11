import aiomysql

async def get_all_logs(pool: aiomysql.Pool):
    """Return all user data from crypto.spoken table"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * from crypto.logging")
            data = await cursor.fetchall()
            return data


async def set_msg_count(pool: aiomysql.Pool, client, gid, uid, msg_count=1):
    """Return user data from rotmg.users table"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(f"SELECT * from crypto.logging WHERE gid = {gid} AND uid = {uid}")
            data = await cursor.fetchone()
            if not data:
                sql = "INSERT INTO crypto.logging (gid, uid, msg_count) VALUES (%s, %s, %s)"
                data = (gid, uid, msg_count)
                await cursor.execute(sql, data)
                client.spoken.get(gid, set()).add(uid)
                return True

async def update_photo_hash(pool: aiomysql.Pool, uid, hash):
    """Update photo hash for a user"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            sql = "INSERT INTO crypto.logging (uid, photo_hash) VALUES (%s, %s) ON DUPLICATE KEY UPDATE photo_hash = %s"
            await cursor.executemany(sql, (uid, hash, hash))
            return True


async def batch_update_photo_hashes(pool: aiomysql.Pool, data):
    """Bulk update photo hashes"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            data = [(r[0], r[1], r[1]) for r in data]
            sql = "INSERT INTO crypto.logging (uid, photo_hash) VALUES (%s, %s) ON DUPLICATE KEY UPDATE photo_hash = %s"
            await cursor.executemany(sql, data)
            return True


async def set_banned_photo(pool: aiomysql.Pool, gid, uid, banned:bool):
    """Update banned photos"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            sql = "INSERT INTO crypto.logging (gid, uid, banned_photo) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE banned_photo = %s"
            await cursor.execute(sql, (gid, uid, banned, banned))
            return True


async def get_photo_hashes(pool: aiomysql.Pool, gid):
    """Get all phto"""
