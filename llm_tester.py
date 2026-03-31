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
        self.root.geometry("1150x650")

        self.config_data = []
        self.row_map = []
        
        # 状态控制变量
        self.stop_pending = False  # 是否请求停止
        self.is_testing = False    # 当前是否正在检测

        # Tooltip 相关
        self.tooltip_window = None
        self.after_id = None
        self.selected_row_id = None

        self.timeout_var = tk.StringVar(value="20")

        self.setup_ui()

    def setup_ui(self):
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)

        self.btn_load = ttk.Button(top_frame, text="加载 YAML 配置", command=self.load_config)
        self.btn_load.pack(side=tk.LEFT, padx=5)

        ttk.Label(top_frame, text="超时(秒):").pack(side=tk.LEFT, padx=(15, 2))
        self.timeout_entry = ttk.Entry(top_frame, textvariable=self.timeout_var, width=5)
        self.timeout_entry.pack(side=tk.LEFT, padx=5)

        # 按钮组
        self.btn_run_selected = ttk.Button(top_frame, text="检测选中项", 
                                          command=lambda: self.start_tests(mode="selected"), state=tk.DISABLED)
        self.btn_run_selected.pack(side=tk.LEFT, padx=5)

        self.btn_run_all = ttk.Button(top_frame, text="检测全部", 
                                     command=lambda: self.start_tests(mode="all"), state=tk.DISABLED)
        self.btn_run_all.pack(side=tk.LEFT, padx=5)

        # 【新增】停止检测按钮
        self.btn_stop = ttk.Button(top_frame, text="停止检测", 
                                  command=self.stop_tests, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.lbl_status = ttk.Label(top_frame, text="请先加载配置文件")
        self.lbl_status.pack(side=tk.RIGHT, padx=5)

        # 表格区域
        table_container = ttk.Frame(self.root, padding="10")
        table_container.pack(fill=tk.BOTH, expand=True)

        columns = ("provider", "model", "status", "latency", "message")
        self.tree = ttk.Treeview(table_container, columns=columns, show="headings", selectmode="extended")
        
        vsb = ttk.Scrollbar(table_container, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(table_container, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.heading("provider", text="接口名称")
        self.tree.heading("model", text="模型 ID")
        self.tree.heading("status", text="状态")
        self.tree.heading("latency", text="响应时间 (ms)")
        self.tree.heading("message", text="详细信息 (选中3秒后弹出详情)")

        for col, width in zip(columns, [120, 150, 100, 120, 800]):
            self.tree.column(col, width=width, minwidth=80)
        self.tree.column("status", anchor=tk.CENTER)
        self.tree.column("latency", anchor=tk.CENTER)

        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')

        table_container.grid_columnconfigure(0, weight=1)
        table_container.grid_rowconfigure(0, weight=1)

        self.tree.tag_configure('success', foreground='green')
        self.tree.tag_configure('fail', foreground='red')
        self.tree.tag_configure('waiting', foreground='gray')
        self.tree.tag_configure('testing', foreground='blue')

        self.tree.bind("<<TreeviewSelect>>", self.on_item_selected)

    def load_config(self):
        file_path = filedialog.askopenfilename(filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")])
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.config_data = yaml.safe_load(f)
            
            self.clear_table()
            self.row_map = []

            for item in self.config_data:
                name = item.get("name", "未命名")
                models = item.get("models", [])
                for model in models:
                    row_id = self.tree.insert("", tk.END, values=(name, model, "等待检测", "-", "-"), tags=('waiting',))
                    self.row_map.append({
                        "row_id": row_id,
                        "name": name, "base_url": item.get("base_url"),
                        "api_key": item.get("api_key"), "model": model
                    })

            self.lbl_status.config(text=f"已加载 {len(self.row_map)} 个测试项")
            self.btn_run_all.config(state=tk.NORMAL)
            self.update_run_selected_button_state()
            
        except Exception as e:
            messagebox.showerror("错误", f"读取配置文件失败: {str(e)}")

    def clear_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def update_run_selected_button_state(self):
        if not self.is_testing:
            state = tk.NORMAL if self.tree.selection() else tk.DISABLED
            self.btn_run_selected.config(state=state)

    def stop_tests(self):
        """点击停止按钮触发"""
        if self.is_testing:
            self.stop_pending = True
            self.btn_stop.config(state=tk.DISABLED)
            self.lbl_status.config(text="正在停止，请稍候...")

    def start_tests(self, mode="all"):
        try:
            self.current_timeout = int(self.timeout_var.get())
            if self.current_timeout <= 0: raise ValueError()
        except ValueError:
            messagebox.showwarning("警告", "超时时间请输入正整数")
            return

        # 更新状态标志
        self.is_testing = True
        self.stop_pending = False

        # 切换按钮状态
        self.btn_run_all.config(state=tk.DISABLED)
        self.btn_run_selected.config(state=tk.DISABLED)
        self.btn_load.config(state=tk.DISABLED)
        self.timeout_entry.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        
        thread = threading.Thread(target=self.run_logic, args=(mode,))
        thread.daemon = True
        thread.start()

    def run_logic(self, mode):
        if mode == "selected":
            selected_ids = self.tree.selection()
            tasks_to_run = [t for t in self.row_map if t["row_id"] in selected_ids]
        else:
            tasks_to_run = self.row_map

        # 重置状态
        for task in tasks_to_run:
            self.tree.item(task["row_id"], values=(task["name"], task["model"], "等待检测", "-", "-"), tags=('waiting',))
        
        self.lbl_status.config(text=f"正在检测 ({len(tasks_to_run)})...")

        for task in tasks_to_run:
            # 【核心检查】如果用户点击了停止，则跳出循环
            if self.stop_pending:
                break

            row_id = task["row_id"]
            self.tree.item(row_id, values=(task["name"], task["model"], "⏳ 测试中...", "-", "-"), tags=('testing',))
            self.tree.see(row_id)
            
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
            # 注意：requests 的调用本身是阻塞的，它会等待 timeout_val。
            # 如果要实现瞬间停止，需要更复杂的逻辑，目前这种方式在当前请求结束后立即停止。
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
        self.is_testing = False
        
        # 恢复按钮状态
        self.btn_run_all.config(state=tk.NORMAL)
        self.btn_load.config(state=tk.NORMAL)
        self.timeout_entry.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.update_run_selected_button_state()

        if self.stop_pending:
            self.lbl_status.config(text="检测已手动停止")
            messagebox.showwarning("已停止", "检测任务已手动停止")
        else:
            self.lbl_status.config(text="检测完成")
            messagebox.showinfo("完成", "检测任务已全部结束")
        
        self.stop_pending = False

    def on_item_selected(self, event):
        self.hide_tooltip()
        self.update_run_selected_button_state()
        
        selection = self.tree.selection()
        if not selection or self.is_testing: # 正在检测时暂不触发 tooltip
            return
        
        self.selected_row_id = selection[-1]
        self.after_id = self.root.after(3000, lambda: self.show_tooltip(self.selected_row_id))

    def show_tooltip(self, row_id):
        if self.is_testing or not self.tree.exists(row_id): return
            
        item_values = self.tree.item(row_id, "values")
        if not item_values or len(item_values) < 5: return
        
        full_text = item_values[4]
        if full_text == "-" or not full_text: return

        bbox = self.tree.bbox(row_id)
        if not bbox: return
        
        root_x = self.tree.winfo_rootx() + bbox[0] + 50
        root_y = self.tree.winfo_rooty() + bbox[1] + bbox[3] + 2

        self.tooltip_window = tk.Toplevel(self.root)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{root_x}+{root_y}")
        self.tooltip_window.attributes("-topmost", True)
        
        frame = tk.Frame(self.tooltip_window, background="#333333", padx=1, pady=1)
        frame.pack()

        label = tk.Label(frame, text=f"详细信息:\n{full_text}", justify=tk.LEFT,
                        background="#ffffe1", relief=tk.FLAT,
                        wraplength=600, padx=10, pady=10, font=("Microsoft YaHei", 9))
        label.pack()
        label.bind("<Button-1>", lambda e: self.hide_tooltip())

    def hide_tooltip(self):
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
