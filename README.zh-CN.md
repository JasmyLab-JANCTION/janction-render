# JANCTION Render（简体中文）

[English](README.md) · 中文说明页面：https://render.janction.jp/zh

JANCTION Render 是面向 AI 智能体的 Blender 云端 GPU 渲染服务，也是一个 MCP 服务器。把 `.blend`、bpy 脚本或 3D 文件（glTF/GLB、FBX、USD、OBJ、STL）交给它，几秒内得到带点评的预览（太暗、过曝、没有灯光、物体出画等，并附修复用的 bpy 代码），确认后在 JANCTION 的 NVIDIA GPU 上渲染静帧或 MP4。本机不需要 Blender 和显卡，也不需要注册。运营方：JasmyLab Inc.（日本东京）。

价格、免费额度和限制以 https://render.janction.jp/zh/pricing 和 https://render.janction.jp/facts.json 为准。新密钥带免费 GPU 时间，无需绑卡；之后按 GPU 秒计费。

## 连接

支持远程 MCP（Streamable HTTP）的客户端，添加：

```
https://render.janction.jp/mcp
```

支持 OAuth 的客户端会打开授权页面并自动生成免费密钥；只能填固定请求头的客户端，用下面的命令获取密钥，放进 `Authorization: Bearer jr_…`：

```shell
curl -X POST https://render.janction.jp/v1/keys
```

| 客户端 | 设置 |
|---|---|
| Qwen Code | `qwen extensions install https://github.com/JasmyLab-JANCTION/janction-render`，或 `qwen mcp add --transport http janction-render https://render.janction.jp/mcp` |
| Kimi Code | `/plugins install https://github.com/JasmyLab-JANCTION/janction-render` |
| DeepSeek Harness | 官方 `@deepseek-ai/dsh-mcp-client`，transport `streamable-http`，请求头放 Bearer 密钥（https://render.janction.jp/zh/deepseek-blender） |
| 只支持 stdio 的客户端 | `{"command": "npx", "args": ["-y", "janction-render"], "env": {"JANCTION_RENDER_API_KEY": "jr_…"}}` |
| 扣子（Coze）、Dify 等没有 MCP 的平台 | 导入 OpenAPI `https://render.janction.jp/openapi-actions.json`，认证用 API Key（请求头 `X-API-Key`） |

Claude、ChatGPT、Claude Code、Codex、Cursor、VS Code 等见 [README.md](README.md)。

## 命令行

国内可以用镜像安装：

```shell
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple janction-render
janction-render try                       # 渲染一个示例，自动生成免费密钥
janction-render preview scene.blend       # 你的 .blend、bpy 脚本或 3D 文件
janction-render render scene.blend --frames 1-96 --size 1280x720 --wait   # 输出 MP4
```

```shell
npx --registry=https://registry.npmmirror.com -y janction-render
```

## 连接后这样说

```
用 JANCTION Render 做一个在灰色地面上旋转的红色光面立方体，先给我看 4 帧预览。
如果没问题，再渲染 24 帧 1280x720 的 MP4。
```

## 说明

- 中文页面：[首页](https://render.janction.jp/zh) · [价格](https://render.janction.jp/zh/pricing) · [Blender MCP](https://render.janction.jp/zh/blender-mcp) · [免费云渲染](https://render.janction.jp/zh/free-blender-cloud-rendering) · [没有显卡](https://render.janction.jp/zh/render-blender-without-gpu) · [动画渲染](https://render.janction.jp/zh/render-blender-animation-online) · [产品 360 度视频](https://render.janction.jp/zh/product-turntable) · [渲染示例](https://render.janction.jp/zh/examples)
- 给 AI 智能体：https://render.janction.jp/zh/llms.txt
- 付款目前只支持信用卡（Stripe），以日元结算；暂不支持支付宝和微信支付。
- 服务器在日本。部分网络环境下访问可能较慢。
