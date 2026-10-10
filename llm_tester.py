import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlsplit, urlunsplit

import requests
import yaml


def normalize_api_url(base_url, endpoint):
    """Build an OpenAI-compatible endpoint URL without corrupting path names."""
    parts = urlsplit(base_url.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("base_url 必须是有效的 http 或 https 地址")
    path = parts.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    path = f"{path}/v1/{endpoint.lstrip('/')}"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def validate_config(data):
    if not isinstance(data, list):
        raise ValueError("配置顶层必须是接口列表")
    validated = []
    for index, item in enumerate(data, 1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 项必须是对象")
        for key in ("name", "base_url", "api_key"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"第 {index} 项的 {key} 必须是非空字符串")
        try:
            normalize_api_url(item["base_url"], "models")
        except ValueError as exc:
            raise ValueError(f"第 {index} 项的 base_url 无效：{exc}") from exc
        validated.append({key: item[key].strip() for key in ("name", "base_url", "api_key")})
    return validated


def extract_model_ids(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("模型列表响应格式无效：缺少 data 数组")
    ids = []
    for item in payload["data"]:
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip():
            ids.append(item["id"].strip())
    return sorted(set(ids), key=str.casefold)


def test_model_api(interface, model, mode, timeout):
    endpoint = "chat/completions" if mode == "Chat Completions" else "responses"
    url = normalize_api_url(interface["base_url"], endpoint)
    headers = {"Authorization": f"Bearer {interface['api_key']}", "Content-Type": "application/json"}
    if mode == "Chat Completions":
        payload = {"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}
    else:
        payload = {"model": model, "input": "hi", "max_output_tokens": 5}
    started = time.perf_counter()
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        elapsed = int((time.perf_counter() - started) * 1000)
        if response.ok:
            return "✅ 可用", elapsed, "Success", "success"
        return "❌ 失败", elapsed, f"HTTP {response.status_code}: {response.text[:2000]}", "fail"
    except requests.exceptions.Timeout:
        return "❌ 超时", "-", f"请求超过 {timeout}s 未响应", "fail"
    except requests.exceptions.RequestException as exc:
        return "❌ 错误", "-", str(exc), "fail"
    except ValueError as exc:
        return "❌ 错误", "-", str(exc), "fail"


class ModelSelectionDialog(tk.Toplevel):
    def __init__(self, parent, models, selected):
        super().__init__(parent)
        self.title("选择模型")
        self.geometry("480x520")
        self.transient(parent)
        self.result = None
        self.models = models
        self.selected = set(selected)
        self.filter_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.filter_var).pack(fill=tk.X, padx=10, pady=(10, 5))
        tools = ttk.Frame(self)
        tools.pack(fill=tk.X, padx=10)
        ttk.Button(tools, text="全选", command=self.select_visible).pack(side=tk.LEFT)
        ttk.Button(tools, text="取消全选", command=self.clear_visible).pack(side=tk.LEFT, padx=5)
        self.listbox = tk.Listbox(self, selectmode=tk.EXTENDED, exportselection=False)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        self.listbox.bind("<<ListboxSelect>>", self.store_visible_selection)
        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(actions, text="取消", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(actions, text="确认", command=self.confirm).pack(side=tk.RIGHT, padx=5)
        self.filter_var.trace_add("write", self.refresh)
        self.refresh()
        self.grab_set()

    def store_visible_selection(self, _event=None):
        if not hasattr(self, "visible"):
            return
        self.selected.difference_update(self.visible)
        self.selected.update(self.visible[i] for i in self.listbox.curselection())

    def refresh(self, *_):
        self.store_visible_selection()
        query = self.filter_var.get().casefold().strip()
        self.visible = [model for model in self.models if query in model.casefold()]
        self.listbox.delete(0, tk.END)
        for model in self.visible:
            self.listbox.insert(tk.END, model)
            if model in self.selected:
                self.listbox.selection_set(tk.END)

    def select_visible(self):
        self.listbox.selection_set(0, tk.END)

    def clear_visible(self):
        self.listbox.selection_clear(0, tk.END)

    def confirm(self):
        visible_selected = {self.visible[i] for i in self.listbox.curselection()}
        self.selected.difference_update(self.visible)
        self.selected.update(visible_selected)
        # Return the API's order; the caller merges it with existing choices so
        # newly added models are appended after models already in the table.
        self.result = [model for model in self.models if model in self.selected]
        self.destroy()


class LLMTesterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LLM API 可用性测试工具")
        self.root.geometry("1180x700")
        self.interfaces = []
        self.selected_models = {}
        self.available_models = {}
        self.rows = {}
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.is_busy = False
        self.pending_fetch_indices = []
        self.timeout_var = tk.StringVar(value="30")
        self.mode_var = tk.StringVar(value="Chat Completions")
        self.build_ui()
        self.root.after(100, self.process_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def build_ui(self):
        bar = ttk.Frame(self.root, padding=8)
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="加载 YAML", command=self.load_config).pack(side=tk.LEFT, padx=3)
        ttk.Button(bar, text="获取模型", command=self.fetch_models).pack(side=tk.LEFT, padx=3)
        ttk.Label(bar, text="模式:").pack(side=tk.LEFT, padx=(12, 3))
        mode_combo = ttk.Combobox(bar, textvariable=self.mode_var, values=("Chat Completions", "Responses"), state="readonly", width=18)
        mode_combo.pack(side=tk.LEFT)
        mode_combo.bind("<<ComboboxSelected>>", self.update_row_modes)
        ttk.Label(bar, text="超时(秒):").pack(side=tk.LEFT, padx=(10, 3))
        ttk.Entry(bar, textvariable=self.timeout_var, width=5).pack(side=tk.LEFT)
        ttk.Button(bar, text="检测选中", command=lambda: self.start_tests(True)).pack(side=tk.LEFT, padx=3)
        ttk.Button(bar, text="检测全部", command=lambda: self.start_tests(False)).pack(side=tk.LEFT, padx=3)
        ttk.Button(bar, text="清除结果", command=self.clear_results).pack(side=tk.LEFT, padx=3)
        self.stop_button = ttk.Button(bar, text="停止", command=self.stop, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=3)
        self.status = ttk.Label(bar, text="请加载接口配置")
        self.status.pack(side=tk.RIGHT)

        panes = ttk.Panedwindow(self.root, orient=tk.VERTICAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)
        interface_frame = ttk.LabelFrame(panes, text="接口（选择接口后获取模型）", padding=5)
        test_frame = ttk.LabelFrame(panes, text="已选模型", padding=5)
        panes.add(interface_frame, weight=1)
        panes.add(test_frame, weight=3)
        self.interface_tree = ttk.Treeview(interface_frame, columns=("name", "url", "models"), show="headings", selectmode="extended", height=5)
        for col, title, width in (("name", "接口名称", 180), ("url", "Base URL", 480), ("models", "已选模型数", 100)):
            self.interface_tree.heading(col, text=title)
            self.interface_tree.column(col, width=width)
        self.interface_tree.pack(fill=tk.BOTH, expand=True)
        self.interface_tree.bind("<Double-1>", self.edit_models)

        columns = ("provider", "model", "mode", "status", "latency", "message")
        self.tree = ttk.Treeview(test_frame, columns=columns, show="headings", selectmode="extended")
        titles = {"provider": "接口", "model": "模型 ID", "mode": "模式", "status": "状态", "latency": "响应时间(ms)", "message": "详情"}
        widths = {"provider": 150, "model": 220, "mode": 150, "status": 100, "latency": 115, "message": 450}
        for col in columns:
            self.tree.heading(col, text=titles[col])
            self.tree.column(col, width=widths[col], minwidth=80)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.tag_configure("success", foreground="green")
        self.tree.tag_configure("fail", foreground="red")
        self.tree.tag_configure("testing", foreground="blue")
        self.tree.bind("<<TreeviewSelect>>", self.show_selected_details)

    def load_config(self):
        if self.is_busy:
            return
        path = filedialog.askopenfilename(filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as stream:
                interfaces = validate_config(yaml.safe_load(stream))
        except (OSError, yaml.YAMLError, ValueError) as exc:
            messagebox.showerror("配置错误", str(exc))
            return
        self.interfaces = interfaces
        self.selected_models = {i: [] for i in range(len(interfaces))}
        self.available_models = {}
        self.refresh_interfaces()
        self.status.config(text=f"已加载 {len(interfaces)} 个接口")

    def refresh_interfaces(self):
        self.interface_tree.delete(*self.interface_tree.get_children())
        for index, item in enumerate(self.interfaces):
            self.interface_tree.insert("", tk.END, iid=str(index), values=(item["name"], item["base_url"], len(self.selected_models.get(index, []))))

    def fetch_models(self):
        indices = [int(i) for i in self.interface_tree.selection()]
        if not indices:
            messagebox.showinfo("提示", "请先选择一个或多个接口")
            return
        if self.is_busy:
            return
        self.is_busy = True
        self.stop_event.clear()
        self.stop_button.config(state=tk.NORMAL)
        self.status.config(text="正在获取模型列表...")
        threading.Thread(target=self.fetch_worker, args=(indices,), daemon=True).start()

    def fetch_worker(self, indices):
        for index in indices:
            if self.stop_event.is_set():
                break
            item = self.interfaces[index]
            try:
                url = normalize_api_url(item["base_url"], "models")
                response = requests.get(url, headers={"Authorization": f"Bearer {item['api_key']}"}, timeout=30)
                response.raise_for_status()
                models = extract_model_ids(response.json())
                self.events.put(("models", index, models, None))
            except (requests.RequestException, ValueError) as exc:
                self.events.put(("models", index, [], str(exc)))
        self.events.put(("fetch_done",))

    def edit_models(self, _event=None):
        selection = self.interface_tree.selection()
        if len(selection) != 1:
            return
        index = int(selection[0])
        known = getattr(self, "available_models", {}).get(index)
        if known is None:
            messagebox.showinfo("提示", "请先获取该接口的模型列表")
            return
        dialog = ModelSelectionDialog(self.root, known, self.selected_models.get(index, []))
        self.root.wait_window(dialog)
        if dialog.result is not None:
            self.update_selected_models(index, dialog.result)
            self.refresh_interfaces()
            self.refresh_test_rows()

    def update_selected_models(self, index, models):
        """Keep existing rows in place and append newly selected models."""
        old_models = self.selected_models.get(index, [])
        chosen = set(models)
        self.selected_models[index] = (
            [model for model in old_models if model in chosen]
            + [model for model in models if model not in old_models]
        )

    def update_row_modes(self, _event=None):
        for iid in self.tree.get_children():
            values = list(self.tree.item(iid, "values"))
            values[2] = self.mode_var.get()
            self.tree.item(iid, values=values)

    def refresh_test_rows(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.rows.clear()
        for index, models in self.selected_models.items():
            for model in models:
                iid = f"{index}:{model}"
                self.rows[iid] = (self.interfaces[index], model)
                self.tree.insert("", tk.END, iid=iid, values=(self.interfaces[index]["name"], model, self.mode_var.get(), "待检测", "-", "-"))

    def clear_results(self):
        """Clear statuses and messages while retaining the selected model list."""
        for iid in self.tree.get_children():
            values = list(self.tree.item(iid, "values"))
            values[3:] = ("待检测", "-", "-")
            self.tree.item(iid, values=values, tags=())
        self.status.config(text="检测结果已清除")

    def show_selected_details(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[-1], "values")
        if len(values) < 6 or values[5] in ("", "-"):
            return
        messagebox.showinfo(
            "完整错误详情",
            f"接口：{values[0]}\n模型：{values[1]}\n模式：{values[2]}\n状态：{values[3]}\n\n{values[5]}",
        )

    def start_tests(self, selected_only):
        try:
            timeout = int(self.timeout_var.get())
            if timeout <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("输入错误", "超时时间请输入正整数")
            return
        if self.is_busy:
            return
        ids = list(self.tree.selection()) if selected_only else list(self.tree.get_children())
        if not ids:
            messagebox.showinfo("提示", "请先获取并选择模型")
            return
        tasks = [(iid, *self.rows[iid]) for iid in ids]
        mode = self.mode_var.get()
        self.is_busy = True
        self.stop_event.clear()
        self.stop_button.config(state=tk.NORMAL)
        self.status.config(text=f"正在检测 {len(tasks)} 个模型...")
        threading.Thread(target=self.test_worker, args=(tasks, mode, timeout), daemon=True).start()

    def test_worker(self, tasks, mode, timeout):
        for iid, interface, model in tasks:
            if self.stop_event.is_set():
                break
            self.events.put(("row", iid, "测试中...", "-", "-", "testing"))
            status, latency, message, tag = test_model_api(interface, model, mode, timeout)
            self.events.put(("row", iid, status, latency, message, tag))
        self.events.put(("test_done",))

    def stop(self):
        self.stop_event.set()
        self.status.config(text="停止请求已提交，当前网络请求结束后停止")
        self.stop_button.config(state=tk.DISABLED)

    def process_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "models":
                    _, index, models, error = event
                    if not hasattr(self, "available_models"):
                        self.available_models = {}
                    if error:
                        messagebox.showerror("获取模型失败", f"{self.interfaces[index]['name']}: {error}")
                    else:
                        self.available_models[index] = models
                        self.status.config(text=f"{self.interfaces[index]['name']} 获取到 {len(models)} 个模型")
                        if index not in self.pending_fetch_indices:
                            self.pending_fetch_indices.append(index)
                elif event[0] == "row":
                    _, iid, status, latency, message, tag = event
                    if self.tree.exists(iid):
                        current = self.tree.item(iid, "values")
                        self.tree.item(iid, values=(current[0], current[1], current[2], status, latency, message), tags=(tag,))
                elif event[0] in {"fetch_done", "test_done"}:
                    self.is_busy = False
                    self.stop_button.config(state=tk.DISABLED)
                    self.status.config(text="检测已停止" if self.stop_event.is_set() else "操作完成")
                    if event[0] == "fetch_done" and self.pending_fetch_indices:
                        fetched_indices = self.pending_fetch_indices
                        self.pending_fetch_indices = []
                        for index in fetched_indices:
                            dialog = ModelSelectionDialog(self.root, self.available_models[index], self.selected_models.get(index, []))
                            self.root.wait_window(dialog)
                            if dialog.result is not None:
                                self.update_selected_models(index, dialog.result)
                        self.refresh_interfaces()
                        self.refresh_test_rows()
        except queue.Empty:
            pass
        self.root.after(100, self.process_events)

    def close(self):
        self.stop_event.set()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    LLMTesterApp(root)
    root.mainloop()
