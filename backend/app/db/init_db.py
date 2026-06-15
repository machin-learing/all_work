from sqlalchemy import select

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.model_option import ModelOption
from app.models.role_option import RoleOption
from app.models.user import User


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_roles = [
            ("boss", "老板", "上级，远距离，工作领域"),
            ("colleague", "同事", "平级，中等距离，工作领域"),
            ("close_friend", "好朋友", "平等，近距离，生活领域"),
            ("girlfriend", "女朋友", "平等，最近距离，恋爱领域"),
            ("mother", "母亲", "晚辈→长辈，近距离，家庭领域"),
        ]
        seed_models = [
            ("deepseek_api", "DeepSeek 教师模型", "千帆 DeepSeek V3.2，真实 API 调用"),
            ("transformer_scratch", "自训练模型", "Transformer 从零训练 baseline"),
            ("lora_finetuned", "微调模型", "预训练模型 + LoRA 微调"),
        ]

        for code, name, desc in seed_roles:
            exists = db.scalar(select(RoleOption).where(RoleOption.code == code))
            if not exists:
                db.add(RoleOption(code=code, name=name, description=desc))

        for code, name, desc in seed_models:
            exists = db.scalar(select(ModelOption).where(ModelOption.code == code))
            if not exists:
                db.add(ModelOption(code=code, name=name, description=desc))

        admin = db.scalar(select(User).where(User.username == "admin"))
        if not admin:
            db.add(
                User(
                    username="admin",
                    full_name="系统管理员",
                    password_hash=hash_password("admin123"),
                    is_admin=True,
                    is_active=True,
                )
            )
        db.commit()
    finally:
        db.close()
