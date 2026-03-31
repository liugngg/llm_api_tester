# LLM_API 可用性测试工具--liug

## 1. 主要功能：

1. 一个测试 LLM_API可用性的图形化工具
2. 输入为LLM API的yaml配置文件，里面包含LLM 的名称、API-key、接口地址、模型ID列表等内容（多个）
3. 利用表格直观输出结果，包括哪些接口哪些模型可用（响应时间），不可用时显示出错原因

## 2. 具体特点：
- 加载配置：点击按钮选择 YAML 文件，程序会自动解析接口和模型列表并显示到表格中。
- 多模型支持：如果一个 API 地址下有多个模型（如 gpt-3.5 和 gpt-4），程序会逐一进行测试。
- 并发与UI响应：使用 threading 库在后台执行网络请求，确保在测试过程中 GUI 界面不会“假死”，用户可以滚动查看已出的结果。
- 直观显示：
    - 成功：显示绿色，标记为 “✅ 可用”，并显示毫秒级的响应延迟。
    - 失败/错误：显示红色，标记为 “❌ 失败” 或 “❌ 错误”，并在最后两列详细展示 HTTP 状态码或具体的 Python 异常信息（如网络连接超时、DNS 错误等）。
    - 超时控制：默认设置了 15 秒超时，防止因某个接口彻底挂掉导致程序长时间卡住。

## 3. 打包命令

- 生成单文件格式
  `pyinstaller -i -F llm_tester.py --clean -n LLM_API可用性测试工具`

- 生成单文件格式（Nuitka --onefile自动压缩）
- 如果你还没有在当前环境中安装 nuitka，你可以使用 --with 参数让 uv 临时安装并运行它，而无需手动 pip install
  `uv run --with nuitka python -m nuitka --mingw64 --onefile --lto=yes --show-progress --output-dir=dist --remove-output llm_tester.py`

- 生成单文件格式（Nuitka --使用upx 压缩）
  `uv run --with nuitka python -m nuitka --mingw64 --onefile --onefile-no-compression --plugin-enable=upx --lto=yes --show-progress --output-dir=dist --remove-output --plugin-enable=tk-inter --windows-console-mode=disable --windows-icon-from-ico=liug.ico llm_tester.py`

## 4. 作者

- [liugngg (GitHub地址)](https://github.com/liugngg)
