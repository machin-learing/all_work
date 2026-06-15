# 文本迁移演示系统

基于 `Vue 3 + FastAPI + MySQL` 的中文多角色文本风格迁移 Demo，支持：

- 用户登录
- 目标角色选择
- 模型类型选择
- 输入语义文本并生成迁移结果
- 历史记录入库与展示
- 管理员查看用户列表

## 目录结构

- `backend`: FastAPI 后端
- `frontend`: Vue 3 前端
- `sql/init.sql`: MySQL 初始化脚本

## 后端启动

```powershell
cd backend
copy .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload
```

默认会自动建表，并初始化：

- 管理员账号：`admin`
- 管理员密码：`admin123`

## 前端启动

```powershell
cd frontend
npm install
npm run dev
```

## MySQL 初始化

```sql
source sql/init.sql;
```

## 真实模型接入

当前模型推理逻辑在 [backend/app/services/model_runner.py](/C:/Users/18317/Desktop/content_rewrite/backend/app/services/model_runner.py:1)。

你后续只需要把 `rewrite_text()` 替换成：

- 本地 Transformer 推理
- LoRA 微调模型推理
- 或外部模型服务调用

接口层和前端无需再改动。
