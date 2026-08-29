# AI Dressing

AI Dressing 是一个 Web MVP：上传服装或穿搭图片后，后端会调用视觉模型识别单品，再生成穿搭建议，并可异步生成搭配参考图。

## 功能

- 单品识别：上传一件衣服，识别颜色、版型、长度、风格标签。
- 这件怎么搭：固定上传单品，生成 3 套搭配方案。
- 这身怎么改：上传整身 Look，先诊断，再给出 recommended / minimal / expressive 三种修改策略。
- 文生图参考：搭配方案先返回文字卡片，图片随后逐张生成并替换。
- 约束校验：后端校验 locked / unavailable / no high heels 等硬约束。

## 技术栈

- Frontend: single-file HTML/CSS/JavaScript
- Backend: FastAPI
- Vision: Qwen Vision
- Styling: DeepSeek
- Image generation: Qwen Image
- Tests: pytest

## 本地运行

安装后端依赖：

```powershell
cd backend
python -m pip install -r requirements.txt
```

复制环境变量文件：

```powershell
copy ..\.env.example .env
```

在 `backend/.env` 中填写真实 API Key。不要提交 `.env`。

启动后端：

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

启动前端：

```powershell
cd ..
python -m http.server 5500
```

打开：

```text
http://127.0.0.1:5500/index.html
```

## 线上部署

推荐部署方式：

- GitHub Pages 托管 `index.html`
- Render / Railway / Fly.io 等平台托管 FastAPI backend

部署后端时需要设置环境变量：

```env
AI_MODE=live
AI_STYLING_MODE=live
AI_IMAGE_MODE=live
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=
QWEN_VISION_MODEL=qwen3.7-plus
QWEN_IMAGE_MODEL=qwen-image-3.0-pro
QWEN_IMAGE_SIZE=928*1664
QWEN_IMAGE_PLAN_LIMIT=1
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-v4-flash
MODEL_TIMEOUT_SECONDS=120
CORS_ORIGINS=https://你的用户名.github.io
```

前端默认请求本地 API。线上体验时，可以在 URL 后追加后端地址：

```text
https://你的用户名.github.io/AI_Dressing/?api=https://你的后端域名/api
```

第一次设置后，前端会把 API 地址保存到浏览器 localStorage。

## 测试

普通测试默认使用 mock，不会调用真实模型：

```powershell
cd backend
python -m pytest
```

真实 DeepSeek 集成测试：

```powershell
$env:RUN_DEEPSEEK_INTEGRATION="1"
python -m pytest tests/test_deepseek_integration.py
```

真实 Qwen Image 集成测试：

```powershell
$env:RUN_QWEN_IMAGE_INTEGRATION="1"
python -m pytest tests/test_qwen_image_integration.py
```

## 安全

- `.env`、`backend/.env`、`backend/uploads/`、`backend/ai_runs.jsonl` 不会提交。
- API Key 只放在后端环境变量中，不能写入前端。
- 文生图当前是搭配参考图，不是严格虚拟试衣。若需要保留用户上传单品的所有细节，应接入图生图/图片编辑/虚拟试衣链路。
