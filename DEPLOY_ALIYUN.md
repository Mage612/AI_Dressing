# 阿里云部署说明

推荐用一个后端服务同时托管网页和 API：访问 `/` 打开前端，前端请求同域名下的 `/api/*`。

## 推荐方案

优先选择阿里云 SAE 或 ECS 的 Docker 部署。

不要只把 `index.html` 放到静态托管里，因为本项目需要 FastAPI 后端调用 Qwen Vision、DeepSeek 和文生图模型。静态网页本身不能安全保存 API Key，也不能稳定执行这些模型请求。

## 环境变量

在线上控制台配置这些环境变量，不要写进代码：

```text
AI_MODE=live
AI_STYLING_MODE=live
AI_IMAGE_MODE=live
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DEEPSEEK_API_KEY=
QWEN_VISION_MODEL=qwen3.7-plus
QWEN_IMAGE_MODEL=qwen-image-3.0-pro
QWEN_IMAGE_SIZE=928*1664
QWEN_IMAGE_PLAN_LIMIT=1
DEEPSEEK_MODEL=deepseek-v4-flash
MODEL_TIMEOUT_SECONDS=180
```

如果前后端同域部署，通常不需要额外配置 CORS。若前端和后端分两个域名部署，再增加：

```text
CORS_ORIGINS=https://你的前端域名
```

## Docker 部署

1. 在云平台创建 Web 服务或容器应用。
2. 连接 GitHub 仓库 `Mage612/AI_Dressing`。
3. 选择 Dockerfile 构建。
4. 暴露端口使用平台提供的 `$PORT`，本项目启动命令已自动读取。
5. 配置上面的环境变量。
6. 健康检查路径填 `/api/health`。

部署成功后访问：

```text
https://你的域名/
```

接口健康检查：

```text
https://你的域名/api/health
```

## 自定义域名

如果使用中国大陆服务器并绑定自己的域名，一般需要完成 ICP 备案。想先快速用于作品集，可以先使用 SAE/ECS 提供的临时公网地址，确认链路稳定后再绑定域名和 HTTPS。

## Vercel 当前问题

Vercel 上只部署静态前端时，页面会请求：

```text
https://你的-vercel-域名/api/upload
https://你的-vercel-域名/api/analyze-item
```

但这些 FastAPI 接口并没有在 Vercel 这个域名下运行，所以会表现为一直识别、识别失败或后端超时。

临时测试可以在 Vercel 地址后面加 `?api=` 指向真实后端：

```text
https://你的-vercel-域名/?api=https://你的后端域名/api
```

作品集正式展示更建议使用“同一个后端服务托管网页和 API”的部署方式。
