# LLM_API 可用性测试工具--liug

## 1. 主要功能：

1. 一个测试 LLM_API 可用性的图形化工具
2. 输入只包含接口名称、API-key 和接口地址的 YAML 配置文件
3. 在界面获取、过滤并多选模型，再测试模型可用性
4. 支持 Chat Completions、Responses 与 Gemini 原生三种请求格式

## 2. 具体特点：
- 加载配置：点击按钮选择 YAML 文件，配置中不需要填写模型 ID。
- 获取模型：先选择请求模式，再选择接口并点击“获取模型”。OpenAI 兼容模式调用 `/v1/models`；Gemini 模式调用 `/v1beta/models`，自动获取所有分页，并排除明确不支持 `generateContent` 的模型。
- 模型选择：模型列表支持过滤、全选、取消全选和多选；选择结果仅保存在当前运行会话，不会写回 YAML。
- 请求模式：可选择 Chat Completions、Responses 或 Gemini；该设置对当前获取模型和检测操作中的所有接口生效，混合配置请分批选择接口操作。
- 并发与UI响应：使用 threading 库在后台执行网络请求，确保在测试过程中 GUI 界面不会“假死”，用户可以滚动查看已出的结果。
- 直观显示：
    - 成功：显示绿色，标记为 “✅ 可用”，并显示毫秒级的响应延迟。
    - 失败/错误：显示红色，标记为 “❌ 失败” 或 “❌ 错误”，并在最后两列详细展示 HTTP 状态码或具体的 Python 异常信息（如网络连接超时、DNS 错误等）。
    - 超时控制：默认设置了 30 秒超时，防止因某个接口彻底挂掉导致程序长时间卡住。

## 3. Gemini 原生接口

在 YAML 中使用以下配置（`config.yaml` 中也包含示例）：

```yaml
- name: "Gemini 官方"
  api_key: "your-gemini-api-key"
  base_url: "https://generativelanguage.googleapis.com/v1beta"
```

在界面将模式切换为 **Gemini**，选择该接口后获取模型并检测。请求使用 `x-goog-api-key` 鉴权，向 `models/{model}:generateContent` 发送 `contents` / `parts` 格式的消息。

`base_url` 可填写域名根地址（自动补 `/v1beta`），也可包含 `/v1beta`、`/v1` 或 `/v1alpha` 版本路径；中转地址中的路径前缀会保留。无需填写模型 ID 或完整 `generateContent` 地址。此模式用于 Gemini 原生 API，不是 OpenAI 兼容接口或需要 OAuth 的 Vertex AI 接口。

参考：[Gemini 模型列表](https://ai.google.dev/api/models)、[内容生成 API](https://ai.google.dev/api/generate-content)。

## 4. 开发验证

```powershell
uv sync
uv run python llm_tester.py
uv run python -m unittest discover -s tests -v
uv run python -m compileall llm_tester.py
```

测试使用 mock 网络响应，不需要真实 API 密钥。

## 5. 打包命令

- 生成单文件格式
  `uv run --with pyinstaller pyinstaller --onefile --windowed --icon liug.ico --clean -n LLM_API可用性测试工具 llm_tester.py`

- 生成单文件格式（Nuitka --onefile自动压缩）
- 如果你还没有在当前环境中安装 nuitka，你可以使用 --with 参数让 uv 临时安装并运行它，而无需手动 pip install
  `uv run --with nuitka python -m nuitka --mingw64 --onefile --lto=yes --show-progress --output-dir=dist --remove-output llm_tester.py`

- 生成单文件格式（Nuitka --使用upx 压缩）
  `uv run --with nuitka python -m nuitka --mingw64 --onefile --onefile-no-compression --plugin-enable=upx --lto=yes --show-progress --output-dir=dist --remove-output --plugin-enable=tk-inter --windows-console-mode=disable --windows-icon-from-ico=liug.ico llm_tester.py`

## 6. 作者

- [liugngg (GitHub地址)](https://github.com/liugngg)
