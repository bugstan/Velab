import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from config import settings
from database import db_manager
from tasks.client import get_task_client, close_task_client

async def check_services():
    print("=== Velab Service Configuration Check ===")
    
    # 1. Check PostgreSQL
    print(f"\n[1/2] Checking PostgreSQL at {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}...")
    try:
        db_manager.initialize()
        print("✅ Database connection pool initialized.")
        
        pool_status = db_manager.get_pool_status()
        print(f"   Pool status: {pool_status}")
        
        from sqlalchemy import text
        with db_manager.get_session() as session:
            result = session.execute(text("SELECT version();")).scalar()
            print(f"✅ Connection successful. PostgreSQL version: {result}")
            
            # Check for vector extension
            vector_check = session.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector';")).scalar()
            if vector_check:
                print("✅ 'pgvector' extension is installed.")
            else:
                print("❌ 'pgvector' extension is NOT found.")
                
            # Check for tables
            from backend.models.base import Base
            from sqlalchemy import inspect
            inspector = inspect(db_manager._engine)
            tables = inspector.get_table_names()
            if tables:
                print(f"✅ Found {len(tables)} tables: {', '.join(tables)}")
            else:
                print("⚠️ No tables found in fota_db. Database schema may not be initialized.")
                
    except Exception as e:
        print(f"❌ PostgreSQL check failed: {str(e)}")
        
    # 2. Check Redis
    print(f"\n[2/2] Checking Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}...")
    try:
        client = await get_task_client()
        queue_info = await client.get_queue_info()
        
        if "error" in queue_info:
            print(f"❌ Redis check failed: {queue_info['error']}")
        else:
            print(f"✅ Redis connection successful.")
            print(f"   Queue info: {queue_info}")
            
        await close_task_client()
    except Exception as e:
        print(f"❌ Redis check failed: {str(e)}")

    print("\n=== Check Complete ===")

if __name__ == "__main__":
    asyncio.run(check_services())
