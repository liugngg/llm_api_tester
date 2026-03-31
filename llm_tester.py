import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import yaml
import requests
import time
import threading

class LLMTesterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LLM API 可用性测试工具")
        self.root.geometry("1100x650")

        self.config_data = []
        self.row_map = []
        
        # Tooltip 相关变量
        self.tooltip_window = None
        self.after_id = None
        self.selected_row_id = None

        # 超时时间变量 (默认 30 秒)
        self.timeout_var = tk.StringVar(value="20")

        self.setup_ui()

    def setup_ui(self):
        # 顶部操作栏
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)

        self.btn_load = ttk.Button(top_frame, text="加载 YAML 配置", command=self.load_config)
        self.btn_load.pack(side=tk.LEFT, padx=5)

        # 超时设置区域
        ttk.Label(top_frame, text="超时(秒):").pack(side=tk.LEFT, padx=(15, 2))
        self.timeout_entry = ttk.Entry(top_frame, textvariable=self.timeout_var, width=5)
        self.timeout_entry.pack(side=tk.LEFT, padx=5)

        self.btn_run = ttk.Button(top_frame, text="开始检测", command=self.start_tests, state=tk.DISABLED)
        self.btn_run.pack(side=tk.LEFT, padx=5)

        self.lbl_status = ttk.Label(top_frame, text="请先加载配置文件")
        self.lbl_status.pack(side=tk.RIGHT, padx=5)

        # --- 表格及滚动条区域 ---
        table_container = ttk.Frame(self.root, padding="10")
        table_container.pack(fill=tk.BOTH, expand=True)

        # 定义列
        columns = ("provider", "model", "status", "latency", "message")
        self.tree = ttk.Treeview(table_container, columns=columns, show="headings", selectmode="browse")
        
        # 创建滚动条
        vsb = ttk.Scrollbar(table_container, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(table_container, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # 表格表头
        self.tree.heading("provider", text="接口名称")
        self.tree.heading("model", text="模型 ID")
        self.tree.heading("status", text="状态")
        self.tree.heading("latency", text="响应时间 (ms)")
        self.tree.heading("message", text="详细信息 (选中3秒后弹出详情)")

        # 列宽设置
        self.tree.column("provider", width=120, minwidth=100)
        self.tree.column("model", width=150, minwidth=100)
        self.tree.column("status", width=100, minwidth=80, anchor=tk.CENTER)
        self.tree.column("latency", width=120, minwidth=100, anchor=tk.CENTER)
        self.tree.column("message", width=800, minwidth=400)

        # 布局
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')

        table_container.grid_columnconfigure(0, weight=1)
        table_container.grid_rowconfigure(0, weight=1)

        # 颜色标签
        self.tree.tag_configure('success', foreground='green')
        self.tree.tag_configure('fail', foreground='red')
        self.tree.tag_configure('waiting', foreground='gray')
        self.tree.tag_configure('testing', foreground='blue')

        # --- 修改绑定事件 ---
        # 绑定选择事件
        self.tree.bind("<<TreeviewSelect>>", self.on_item_selected)

    def load_config(self):
        file_path = filedialog.askopenfilename(filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")])
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.config_data = yaml.safe_load(f)
            
            if not isinstance(self.config_data, list):
                raise ValueError("YAML 格式错误：顶层应为列表")
            
            self.clear_table()
            self.row_map = []

            for item in self.config_data:
                name = item.get("name", "未命名")
                models = item.get("models", [])
                for model in models:
                    row_id = self.tree.insert("", tk.END, values=(name, model, "等待检测", "-", "-"), tags=('waiting',))
                    self.row_map.append({
                        "row_id": row_id,
                        "name": name,
                        "base_url": item.get("base_url"),
                        "api_key": item.get("api_key"),
                        "model": model
                    })

            self.lbl_status.config(text=f"已加载 {len(self.row_map)} 个测试项")
            self.btn_run.config(state=tk.NORMAL)
            
        except Exception as e:
            messagebox.showerror("错误", f"读取配置文件失败: {str(e)}")

    def clear_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def start_tests(self):
        # 获取并校验超时时间
        try:
            self.current_timeout = int(self.timeout_var.get())
            if self.current_timeout <= 0: raise ValueError()
        except ValueError:
            messagebox.showwarning("警告", "超时时间请输入正整数")
            return

        self.btn_run.config(state=tk.DISABLED)
        self.btn_load.config(state=tk.DISABLED)
        self.timeout_entry.config(state=tk.DISABLED)
        
        thread = threading.Thread(target=self.run_logic)
        thread.daemon = True
        thread.start()

    def run_logic(self):
        for task in self.row_map:
            row_id = task["row_id"]
            self.tree.item(row_id, values=(task["name"], task["model"], "⏳ 测试中...", "-", "-"), tags=('testing',))
            
            status, latency, msg, tag = self.test_api(task["base_url"], task["api_key"], task["model"], self.current_timeout)
            
            self.tree.item(row_id, values=(task["name"], task["model"], status, latency, msg), tags=(tag,))
            self.root.update_idletasks()

        self.root.after(0, self.finish_tests)

    def test_api(self, base_url, api_key, model_id, timeout_val):
        url = f"{base_url.rstrip('/').rstrip('/v1')}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": model_id, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}

        start_time = time.time()
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout_val)
            latency = int((time.time() - start_time) * 1000)
            if response.status_code == 200:
                return ("✅ 可用", latency, "Success", "success")
            else:
                return ("❌ 失败", latency, f"HTTP {response.status_code}: {response.text}", "fail")
        except requests.exceptions.Timeout:
            return ("❌ 超时", "-", f"请求超过 {timeout_val}s 未响应", "fail")
        except Exception as e:
            return ("❌ 错误", "-", str(e), "fail")

    def finish_tests(self):
        self.btn_run.config(state=tk.NORMAL)
        self.btn_load.config(state=tk.NORMAL)
        self.timeout_entry.config(state=tk.NORMAL)
        self.lbl_status.config(text="检测完成")
        messagebox.showinfo("完成", "所有接口检测任务已结束")

    # --- 新的 Tooltip 触发逻辑 ---
    def on_item_selected(self, event):
        """当用户选中某一行时触发"""
        # 1. 立即清除之前的计时器和现有的窗口
        self.hide_tooltip()
        
        # 2. 获取当前选中的行
        selection = self.tree.selection()
        if not selection:
            return
        
        self.selected_row_id = selection[0]
        
        # 3. 启动 3 秒计时器
        self.after_id = self.root.after(3000, lambda: self.show_tooltip(self.selected_row_id))

    def show_tooltip(self, row_id):
        """显示详细信息弹窗"""
        if not self.tree.exists(row_id):
            return
            
        item_values = self.tree.item(row_id, "values")
        if not item_values or len(item_values) < 5:
            return
        
        full_text = item_values[4]
        if full_text == "-" or not full_text:
            return

        # 获取选中行在屏幕上的位置
        # bbox 返回 (x, y, w, h)
        bbox = self.tree.bbox(row_id)
        if not bbox:
            return
        
        # 计算弹出位置（在选中行下方显示）
        root_x = self.tree.winfo_rootx() + bbox[0] + 50
        root_y = self.tree.winfo_rooty() + bbox[1] + bbox[3] + 2

        self.tooltip_window = tk.Toplevel(self.root)
        self.tooltip_window.wm_overrideredirect(True) # 无边框
        self.tooltip_window.wm_geometry(f"+{root_x}+{root_y}")
        self.tooltip_window.attributes("-topmost", True) # 置顶
        
        # 容器框架（美化边框）
        frame = tk.Frame(self.tooltip_window, background="#333333", padx=1, pady=1)
        frame.pack()

        label = tk.Label(frame, text=f"详细信息:\n{full_text}", justify=tk.LEFT,
                        background="#ffffe1", relief=tk.FLAT,
                        wraplength=600, padx=10, pady=10, font=("Microsoft YaHei", 9))
        label.pack()
        
        # 点击弹窗任何地方消失
        label.bind("<Button-1>", lambda e: self.hide_tooltip())

    def hide_tooltip(self):
        """取消计时并销毁弹窗"""
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

if __name__ == "__main__":
    root = tk.Tk()
    app = LLMTesterApp(root)
    root.mainloop()
