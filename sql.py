import enum

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
                await conn.commit()
                client.spoken.get(gid, set()).add(uid)
                return True

async def get_msg_count(pool: aiomysql.Pool, gid, uid):
    """Return user data from rotmg.users table"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(f"SELECT * from crypto.logging WHERE gid = {gid} AND uid = {uid}")
            data = await cursor.fetchone()
            if not data:
                sql = "INSERT INTO crypto.logging (gid, uid, msg_count) VALUES (%s, %s, %s)"
                data = (gid, uid, 0)
                await cursor.execute(sql, data)
                await conn.commit()
                return 0
            else:
                return data[log_cols.msg_count]

async def update_photo_hash(pool: aiomysql.Pool, uid, hash, gid=None, new=True):
    """Update photo hash for a user"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            if new:
                sql = "INSERT INTO crypto.logging (gid, uid, photo_hash) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE photo_hash = values(photo_hash)"
                await cursor.execute(sql, (gid, uid, hash))
            else:
                sql = "UPDATE crypto.logging SET photo_hash = %s WHERE uid = %s"
                await cursor.execute(sql, (hash, uid))
            await conn.commit()
            return True


async def batch_update_photo_hashes(pool: aiomysql.Pool, data):
    """Bulk update photo hashes"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            sql = "INSERT INTO crypto.logging (gid, uid, photo_hash) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE photo_hash = values(photo_hash)"
            await cursor.executemany(sql, data)
            await conn.commit()
            return True


async def set_banned_photo(pool: aiomysql.Pool, gid, uid, banned:bool):
    """Update banned photos"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            sql = "INSERT INTO crypto.logging (gid, uid, banned_photo) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE banned_photo = values(banned_photo)"
            await cursor.execute(sql, (gid, uid, banned))
            await conn.commit()
            return True



class log_cols(enum.IntEnum):
    gid: int = 0
    uid: int = 1
    msg_count: int = 2
    report_count: int = 3
    photo_hash: str = 4
    banned_photo: bool = 5
