"""
SQLAlchemy基础配置

定义所有ORM模型的基类和通用配置
"""

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import MetaData

# 定义命名约定,确保索引和约束名称一致
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)

# 创建声明式基类
Base = declarative_base(metadata=metadata)
