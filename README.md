# LLM_API 可用性测试工具--liug

## 1. 主要功能：

1. 一个测试 LLM_API 可用性的图形化工具
2. 输入只包含接口名称、API-key 和接口地址的 YAML 配置文件
3. 在界面获取、过滤并多选模型，再测试模型可用性
4. 支持 Chat Completions 与 Responses 两种请求格式

## 2. 具体特点：
- 加载配置：点击按钮选择 YAML 文件，配置中不需要填写模型 ID。
- 获取模型：选择接口后点击“获取模型”，程序调用兼容 OpenAI 的 `/v1/models` 接口。
- 模型选择：模型列表支持过滤、全选、取消全选和多选；选择结果仅保存在当前运行会话，不会写回 YAML。
- 请求模式：可选择 Chat Completions 或 Responses。
- 并发与UI响应：使用 threading 库在后台执行网络请求，确保在测试过程中 GUI 界面不会“假死”，用户可以滚动查看已出的结果。
- 直观显示：
    - 成功：显示绿色，标记为 “✅ 可用”，并显示毫秒级的响应延迟。
    - 失败/错误：显示红色，标记为 “❌ 失败” 或 “❌ 错误”，并在最后两列详细展示 HTTP 状态码或具体的 Python 异常信息（如网络连接超时、DNS 错误等）。
    - 超时控制：默认设置了 30 秒超时，防止因某个接口彻底挂掉导致程序长时间卡住。

## 3. 打包命令

- 生成单文件格式
  `uv run --with pyinstaller pyinstaller --onefile --windowed --icon liug.ico --clean -n LLM_API可用性测试工具 llm_tester.py`

- 生成单文件格式（Nuitka --onefile自动压缩）
- 如果你还没有在当前环境中安装 nuitka，你可以使用 --with 参数让 uv 临时安装并运行它，而无需手动 pip install
  `uv run --with nuitka python -m nuitka --mingw64 --onefile --lto=yes --show-progress --output-dir=dist --remove-output llm_tester.py`

- 生成单文件格式（Nuitka --使用upx 压缩）
  `uv run --with nuitka python -m nuitka --mingw64 --onefile --onefile-no-compression --plugin-enable=upx --lto=yes --show-progress --output-dir=dist --remove-output --plugin-enable=tk-inter --windows-console-mode=disable --windows-icon-from-ico=liug.ico llm_tester.py`

## 4. 作者

- [liugngg (GitHub地址)](https://github.com/liugngg)
