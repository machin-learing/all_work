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

当前模型推理逻辑在 `backend/app/services/model_runner.py`。

你后续只需要把 `rewrite_text()` 替换成：

- 本地 Transformer 推理
- LoRA 微调模型推理
- 或外部模型服务调用

接口层和前端无需再改动。

## GitHub 仓库说明

为方便上传和协作，仓库中只保留源码、报告、少量训练样例数据和项目说明，不提交以下可重新生成或体积较大的内容：

- `frontend/node_modules/`：前端依赖，拉取后在 `frontend` 目录执行 `npm install` 安装。
- `frontend/dist/`：前端构建产物，需要时执行 `npm run build` 重新生成。
- `dataset/lccc_data/`：原始 LCCC 数据和教师模型生成中间数据，可通过 `dataset/` 下脚本重新生成。
- `finetune/models/`：本地下载的基座模型，体积较大，不上传仓库。
- `finetune/output/`：训练 checkpoint 和 LoRA 输出，不上传仓库。
- `backend/.env`：本地密钥和数据库配置，不上传仓库；需要时复制 `backend/.env.example` 为 `.env` 后自行填写。
- LaTeX 中间文件：例如 `.aux`、`.log`、`.out`、`.toc`，只保留 `.tex` 源文件和已生成的 PDF。

当前保留的 `finetune/data/train.jsonl`、`finetune/data/val.jsonl`、`finetune/data/test.jsonl` 可供同学查看训练样本格式、撰写数据和模型训练相关报告内容。

## 文档撰写任务分工

以下分工用于补充 `paper/literature_review.tex` 和 `paper/research_practice.tex`。每位同学根据自己负责的模块补充文字、表格、截图或实验结果，最后统一整合格式。

| 成员 | 文献综述负责部分 | 科研实训报告负责部分 | 建议交付物 |
|---|---|---|---|
| 王浩楠 | 研究背景、研究意义、现有研究不足、本项目定位 | 实验概述、研究目标、整体结构整合、总结与展望 | 项目总体说明、技术路线说明、最终报告整合版 |
| 张博凇 | 预训练模型、mT5/mT0、指令微调、LoRA 相关文献 | 模型设计、训练数据格式、LoRA 微调配置、训练过程与问题处理 | 训练参数表、模型输入模板、训练问题记录、模型对比结果 |
| 范智杰 | 中文对话数据集、LCCC、弱监督数据构建、数据质量控制相关文献 | 数据来源、中性句抽取、教师模型改写、质量过滤、数据统计与问题样例 | 数据处理流程、过滤规则说明、数据统计表、低质量样本案例 |
| 何顺康 | 文本风格迁移任务定义、风格迁移评价指标、人工评价方法 | 前端功能、五角色对比、多模型对比、系统截图、用户交互展示 | 前端页面截图、五角色对比样例、多模型对比样例、人工评价表 |
| 陈佳铭 | 系统化实现、模型部署、Web 演示平台相关研究补充 | 后端架构、接口设计、数据库设计、用户鉴权、历史记录存储 | 后端接口表、数据库表说明、接口测试结果、系统调用流程 |

### 具体撰写要求

1. **文献综述部分**
   - 每位同学至少补充 2-3 篇与自己模块相关的参考文献。
   - 写作重点不是堆文献，而是说明这些研究对本项目有什么启发。
   - 可以补充到“相关研究路线对比”“本项目评价维度设计”“中文角色风格数据集构建思路”等小节中。

2. **科研实训报告部分**
   - 每位同学优先补自己实际负责的工作，不要写成空泛介绍。
   - 尽量提供可验证材料，例如截图、表格、样例、接口测试结果、训练配置或错误案例。
   - 当前报告中带有“待补充”的表格和截图占位，大家可以直接替换为真实内容。

3. **统一格式**
   - 正文统一写入 `paper/research_practice.tex` 或 `paper/literature_review.tex`。
   - 系统截图建议放到 `paper/figures/` 目录。
   - 表格标题、图片标题要能说明内容，不要只写“截图1”“表1”。
   - 涉及数据和实验结果时，尽量注明数据来源、测试样本数量和评价方式。
