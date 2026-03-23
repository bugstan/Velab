# AI_Veh

车辆 FOTA 诊断演示：FastAPI（MiniMax + Agent 编排 + SSE）与 Next.js 前端。

## 结构

- `backend/` — Python API，见 `backend/.env.example`
- `web/` — Next.js 前端，见 `web/README.md`
- `data/samples/` — 可选样本资源

## 本地运行（简述）

```bash
# 后端（需在 backend 配置 .env）
cd backend && pip install -r requirements.txt && python main.py

# 前端
cd web && npm install && npm run dev
```

## 推送到 GitHub

在 [GitHub](https://github.com/new) 新建空仓库（不要勾选添加 README），然后：

```bash
cd /path/to/AI_Veh
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

若使用 [GitHub CLI](https://cli.github.com/)：

```bash
gh auth login
gh repo create <仓库名> --private --source=. --remote=origin --push
```

**注意：** 勿提交 `backend/.env`、API Key；仅提交 `.env.example`。
