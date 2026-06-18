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

当前分工以“科研实训报告由王浩楠统一完成，文献综述由其他成员分模块补充”为原则。这样可以保证实验路线、代码实现、结果分析和最终报告口径一致；其他成员重点补充文献综述和少量可验证材料。

| 成员   | 主要负责内容                           | 对应文献综述章节                                                               | 具体任务                                                                                                                                                         | 建议交付物                                                           |
| ------ | -------------------------------------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| 王浩楠 | 科研实训报告主责、最终整合             | 全文统稿；重点检查“引言”“研究不足与本文定位”“结论”                           | 负责 `paper/research_practice.tex` 的实验概述、数据流程、模型训练、系统实现、结果分析、总结与展望；统一检查 `paper/literature_review.tex` 与实训主题是否一致 | 科研实训报告最终版、技术路线说明、实验结果表、系统截图整理、最终 PDF |
| 张博凇 | 文献综述：预训练模型与参数高效微调     | `预训练模型与指令微调`、`参数高效微调技术`                                     | 补充 mT5/mT0、指令微调、LoRA、Adapter/Prefix-Tuning 等相关研究，说明为什么本项目采用 mT0-large + 单 LoRA                                                         | 2-3 篇相关文献总结、模型路线对比表、可放入综述的 LaTeX 文本          |
| 范智杰 | 文献综述：中文对话数据与弱监督数据构建 | `中文对话数据资源`，以及数据质量、角色标注缺口、数据构建思路相关小节           | 补充 LCCC、中文对话数据集、LLM 教师模型生成数据、数据清洗与质量控制相关研究                                                                                      | 2-3 篇相关文献总结、数据构建路线说明、过滤规则文献依据               |
| 何顺康 | 文献综述：文本风格迁移与评价方法       | `文本风格迁移研究`、`本项目评价维度设计`                                       | 补充文本风格迁移任务定义、正式度/情感/作者风格迁移、自动评价与人工评价方法                                                                                       | 2-3 篇相关文献总结、评价维度说明、人工评价表建议                     |
| 陈佳铭 | 文献综述：系统实现与模型部署           | `研究不足与本文定位` 中的系统化实现部分，可补充 Web 演示平台和模型部署相关段落 | 补充 Web 演示系统、模型服务化、前后端交互、用户记录存储等系统化实现相关材料                                                                                      | 2-3 篇相关资料或文献总结、系统平台相关综述文字、接口/部署说明材料    |

### 具体撰写要求

1. **文献综述部分**

   - 每位同学尽量补充 2-3 篇与自己模块相关的参考文献。
   - 写作重点不是堆文献，而是说明这些研究对本项目有什么启发。
   - 可以补充到“相关研究路线对比”“本项目评价维度设计”“中文角色风格数据集构建思路”等小节中。
2. **科研实训报告部分**

   - 科研实训报告由王浩楠统一维护，其他成员不需要大段改写报告主体。
   - 如果自己模块有真实材料，可以单独发给王浩楠整合，例如截图、表格、样例、接口测试结果、训练配置或错误案例。
   - 当前报告中带有“待补充”的表格和截图占位，最终由王浩楠统一替换为真实内容。
3. **统一格式**

   - 正文统一写入 `paper/research_practice.tex` 或 `paper/literature_review.tex`。
   - 系统截图建议放到 `paper/figures/` 目录。
   - 表格标题、图片标题要能说明内容，不要只写“截图1”“表1”。
   - 涉及数据和实验结果时，尽量注明数据来源、测试样本数量和评价方式。

## MiKTeX 安装与 LaTeX 编译说明

本项目报告使用 LaTeX 编写，源码位于 `paper/` 目录：

- `paper/research_practice.tex`：科研实训报告。
- `paper/literature_review.tex`：文献综述。

Windows 同学建议安装 MiKTeX，用于把 `.tex` 文件编译成 PDF。

### 下载安装

1. 打开 MiKTeX 官网：[https://miktex.org/download](https://miktex.org/download)
2. 下载 Windows 版本安装包。
3. 安装时选择默认配置即可；如果出现 “Install missing packages on-the-fly”，建议选择 `Yes` 或 `Ask me first`，这样缺少宏包时 MiKTeX 会自动安装。
4. 安装完成后，打开 PowerShell，执行：

```powershell
xelatex --version
```

如果能看到版本信息，说明安装成功。

### 编译报告

由于报告使用中文，必须用 `xelatex` 编译，不要用 `pdflatex`。

```powershell
cd paper
xelatex research_practice.tex
xelatex research_practice.tex
xelatex literature_review.tex
xelatex literature_review.tex
```

通常需要连续编译两次，目录、引用和交叉引用才能完整更新。

### 推荐编辑方式

可以使用以下任一方式编辑：

- 直接用 VS Code 打开 `.tex` 文件，安装 LaTeX Workshop 插件后编译。
- 使用 MiKTeX 自带的 TeXworks 打开 `.tex` 文件，在左上角编译器选择 `XeLaTeX`，点击绿色运行按钮。

### 常见问题

- 中文乱码或中文无法显示：确认使用的是 `xelatex`，并且 `.tex` 文件保存为 UTF-8 编码。
- 提示缺少宏包：在弹窗中允许 MiKTeX 自动安装；如果没有弹窗，可以打开 MiKTeX Console 更新包数据库。
- 生成很多 `.aux`、`.log`、`.out`、`.toc` 文件：这些是 LaTeX 中间文件，不需要提交到仓库。
- 只改文字不改结构时，可以只提交 `.tex`；如果重新编译了最终报告，也可以一并更新对应 PDF。
