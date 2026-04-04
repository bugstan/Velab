"""
数据库连接管理模块

提供数据库连接池、会话管理和批量操作功能
"""

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator, List, Optional
import logging

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from backend.config import settings
from backend.models.base import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    数据库管理器
    
    负责管理数据库连接池、会话创建和批量操作
    支持同步和异步两种模式
    """
    
    def __init__(self):
        """初始化数据库管理器"""
        self._engine = None
        self._async_engine = None
        self._session_factory = None
        self._async_session_factory = None
        self._initialized = False
    
    def initialize(
        self,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        echo: bool = False
    ):
        """
        初始化数据库连接池
        
        Args:
            pool_size: 连接池大小
            max_overflow: 最大溢出连接数
            pool_timeout: 连接超时时间(秒)
            pool_recycle: 连接回收时间(秒)
            echo: 是否打印SQL语句
        """
        if self._initialized:
            logger.warning("数据库已经初始化,跳过重复初始化")
            return
        
        # 同步引擎
        self._engine = create_engine(
            settings.DATABASE_URL,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=True,  # 连接前ping检查
            echo=echo,
        )
        
        # 异步引擎
        async_url = settings.DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://')
        self._async_engine = create_async_engine(
            async_url,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=True,
            echo=echo,
        )
        
        # 会话工厂
        self._session_factory = sessionmaker(
            bind=self._engine,
            class_=Session,
            expire_on_commit=False,
        )
        
        self._async_session_factory = async_sessionmaker(
            bind=self._async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        # 注册事件监听器
        self._register_event_listeners()
        
        self._initialized = True
        logger.info(f"数据库连接池初始化成功: pool_size={pool_size}, max_overflow={max_overflow}")
    
    def _register_event_listeners(self):
        """注册数据库事件监听器"""
        
        @event.listens_for(self._engine, "connect")
        def receive_connect(dbapi_conn, connection_record):
            """连接建立时的回调"""
            logger.debug("新数据库连接已建立")
        
        @event.listens_for(self._engine, "checkout")
        def receive_checkout(dbapi_conn, connection_record, connection_proxy):
            """从连接池获取连接时的回调"""
            logger.debug("从连接池获取连接")
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        获取同步数据库会话(上下文管理器)
        
        使用示例:
            with db_manager.get_session() as session:
                case = session.query(Case).filter_by(case_id='xxx').first()
        
        Yields:
            Session: 数据库会话对象
        """
        if not self._initialized:
            raise RuntimeError("数据库未初始化,请先调用initialize()")
        
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"数据库操作失败: {e}")
            raise
        finally:
            session.close()
    
    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        获取异步数据库会话(异步上下文管理器)
        
        使用示例:
            async with db_manager.get_async_session() as session:
                result = await session.execute(select(Case).filter_by(case_id='xxx'))
                case = result.scalar_one_or_none()
        
        Yields:
            AsyncSession: 异步数据库会话对象
        """
        if not self._initialized:
            raise RuntimeError("数据库未初始化,请先调用initialize()")
        
        session = self._async_session_factory()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"异步数据库操作失败: {e}")
            raise
        finally:
            await session.close()
    
    def create_tables(self):
        """创建所有表(同步)"""
        if not self._initialized:
            raise RuntimeError("数据库未初始化,请先调用initialize()")
        
        Base.metadata.create_all(bind=self._engine)
        logger.info("数据库表创建成功")
    
    async def create_tables_async(self):
        """创建所有表(异步)"""
        if not self._initialized:
            raise RuntimeError("数据库未初始化,请先调用initialize()")
        
        async with self._async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("数据库表创建成功(异步)")
    
    def drop_tables(self):
        """删除所有表(同步,谨慎使用!)"""
        if not self._initialized:
            raise RuntimeError("数据库未初始化,请先调用initialize()")
        
        Base.metadata.drop_all(bind=self._engine)
        logger.warning("数据库表已删除")
    
    def close(self):
        """关闭数据库连接池"""
        if self._engine:
            self._engine.dispose()
            logger.info("同步数据库连接池已关闭")
        
        if self._async_engine:
            # 异步引擎需要在异步上下文中关闭
            logger.info("异步数据库连接池需要在异步上下文中关闭")
        
        self._initialized = False
    
    async def close_async(self):
        """关闭异步数据库连接池"""
        if self._async_engine:
            await self._async_engine.dispose()
            logger.info("异步数据库连接池已关闭")
        
        self._initialized = False
    
    def get_pool_status(self) -> dict:
        """获取连接池状态"""
        if not self._initialized or not self._engine:
            return {"status": "未初始化"}
        
        pool = self._engine.pool
        return {
            "size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "total": pool.size() + pool.overflow(),
        }


# 全局数据库管理器实例
db_manager = DatabaseManager()


# 便捷函数
def init_db(
    pool_size: int = 10,
    max_overflow: int = 20,
    echo: bool = False
):
    """
    初始化数据库连接池(便捷函数)
    
    Args:
        pool_size: 连接池大小
        max_overflow: 最大溢出连接数
        echo: 是否打印SQL语句
    """
    db_manager.initialize(
        pool_size=pool_size,
        max_overflow=max_overflow,
        echo=echo
    )


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话(FastAPI依赖注入)
    
    使用示例:
        @app.get("/cases/{case_id}")
        def get_case(case_id: str, db: Session = Depends(get_db)):
            return db.query(Case).filter_by(case_id=case_id).first()
    """
    with db_manager.get_session() as session:
        yield session


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取异步数据库会话(FastAPI依赖注入)
    
    使用示例:
        @app.get("/cases/{case_id}")
        async def get_case(case_id: str, db: AsyncSession = Depends(get_async_db)):
            result = await db.execute(select(Case).filter_by(case_id=case_id))
            return result.scalar_one_or_none()
    """
    async with db_manager.get_async_session() as session:
        yield session
