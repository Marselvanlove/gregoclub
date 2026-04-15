#!/usr/bin/env python3
"""
Миграция: Добавление функционала проверки входа в группу
Добавляет:
- users.last_purchase_at (DateTime, nullable)
- users.group_join_check_sent (Boolean, default False)
- Таблица unauthorized_members
"""
import asyncio
import sqlite3
from pathlib import Path


async def migrate():
    """Применяет миграцию к базе данных."""
    db_path = Path(__file__).parent / "data" / "app.db"
    
    if not db_path.exists():
        print(f"❌ База данных не найдена: {db_path}")
        return
    
    print(f"📊 Применяю миграцию к базе: {db_path}")
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Проверяем, существует ли столбец last_purchase_at
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if "last_purchase_at" not in columns:
            print("➕ Добавляю столбец users.last_purchase_at...")
            cursor.execute("""
                ALTER TABLE users 
                ADD COLUMN last_purchase_at DATETIME
            """)
            print("✅ Столбец users.last_purchase_at добавлен")
        else:
            print("⏭️  Столбец users.last_purchase_at уже существует")
        
        if "group_join_check_sent" not in columns:
            print("➕ Добавляю столбец users.group_join_check_sent...")
            cursor.execute("""
                ALTER TABLE users 
                ADD COLUMN group_join_check_sent INTEGER NOT NULL DEFAULT 0
            """)
            print("✅ Столбец users.group_join_check_sent добавлен")
        else:
            print("⏭️  Столбец users.group_join_check_sent уже существует")
        
        # Проверяем, существует ли таблица unauthorized_members
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='unauthorized_members'
        """)
        
        if not cursor.fetchone():
            print("➕ Создаю таблицу unauthorized_members...")
            cursor.execute("""
                CREATE TABLE unauthorized_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id BIGINT NOT NULL UNIQUE,
                    full_name VARCHAR(256),
                    username VARCHAR(64),
                    joined_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX ix_unauthorized_members_telegram_id 
                ON unauthorized_members (telegram_id)
            """)
            print("✅ Таблица unauthorized_members создана")
        else:
            print("⏭️  Таблица unauthorized_members уже существует")
        
        conn.commit()
        print("\n✅ Миграция успешно применена!")
        
    except Exception as e:
        print(f"\n❌ Ошибка при применении миграции: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
