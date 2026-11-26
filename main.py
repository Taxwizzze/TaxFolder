import os
import shutil
import hashlib
import threading
import datetime
import json
import csv
import customtkinter as ctk
from tkinter import filedialog, messagebox

# ============ НАСТРОЙКИ ============
CONFIG_FILE = "config.json"
THEME_FILE = "theme.json"

DEFAULT_CATEGORIES = {
    "Документы": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv"],
    "Фото": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic"],
    "Видео": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"],
    "Музыка": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"],
    "Архивы": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
    "Установщики": [".exe", ".msi", ".dmg", ".pkg", ".apk"],
    "Код": [".py", ".js", ".html", ".css", ".java", ".cpp", ".c", ".h", ".json", ".xml", ".sql"],
    "Другое": []
}

DEFAULT_EXCLUDE = ["Архив", "Windows", "Program Files", "Program Files (x86)", "$Recycle.Bin"]


# ============ КОНФИГ ============
def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                cfg.setdefault("categories", DEFAULT_CATEGORIES.copy())
                cfg.setdefault("exclude", DEFAULT_EXCLUDE.copy())
                return cfg
        except Exception:
            pass
    cfg = {"categories": DEFAULT_CATEGORIES.copy(), "exclude": DEFAULT_EXCLUDE.copy()}
    save_config(cfg)
    return cfg


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_theme() -> str:
    if os.path.exists(THEME_FILE):
        try:
            with open(THEME_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("theme", "dark")
        except Exception:
            pass
    return "dark"


def save_theme(theme: str):
    with open(THEME_FILE, "w", encoding="utf-8") as f:
        json.dump({"theme": theme}, f)


# ============ КАТЕГОРИИ ============
def get_category(ext: str, categories: dict) -> str:
    ext = ext.lower()
    for cat, exts in categories.items():
        if ext in exts:
            return cat
    return "Другое"


def human_size(size: int) -> str:
    for unit in ["Б", "КБ", "МБ", "ГБ"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ТБ"


def file_hash(path: str) -> str:
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def is_excluded(path: str, exclude: list) -> bool:
    parts = path.replace("\\", "/").split("/")
    return any(e in parts for e in exclude)


# ============ СКАНИРОВАНИЕ ============
def scan_folder(root: str, categories: dict, exclude: list) -> dict:
    stats = {
        "total_files": 0,
        "total_size": 0,
        "by_category": {},
        "duplicates": [],
        "old_files": [],
    }
    hash_map = {}
    now = datetime.datetime.now()

    for dirpath, _, filenames in os.walk(root):
        if is_excluded(dirpath, exclude):
            continue
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            if is_excluded(fpath, exclude):
                continue
            try:
                size = os.path.getsize(fpath)
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
            except Exception:
                continue
            stats["total_files"] += 1
            stats["total_size"] += size
            ext = os.path.splitext(fname)[1].lower()
            cat = get_category(ext, categories)
            stats["by_category"].setdefault(cat, {"count": 0, "size": 0})
            stats["by_category"][cat]["count"] += 1
            stats["by_category"][cat]["size"] += size

            h = file_hash(fpath)
            if h:
                if h in hash_map:
                    stats["duplicates"].append((fpath, hash_map[h]))
                else:
                    hash_map[h] = fpath

            if (now - mtime).days > 180:
                stats["old_files"].append(fpath)

    return stats


def sort_files(root: str, categories: dict, exclude: list, progress_cb=None) -> dict:
    moved = 0
    errors = 0
    for dirpath, _, filenames in os.walk(root):
        if is_excluded(dirpath, exclude):
            continue
        if os.path.basename(dirpath) in categories:
            continue
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            ext = os.path.splitext(fname)[1].lower()
            cat = get_category(ext, categories)
            target_dir = os.path.join(root, cat)
            os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, fname)
            base, e = os.path.splitext(fname)
            counter = 1
            while os.path.exists(target_path):
                target_path = os.path.join(target_dir, f"{base}_{counter}{e}")
                counter += 1
            try:
                shutil.move(fpath, target_path)
                moved += 1
            except Exception:
                errors += 1
            if progress_cb:
                progress_cb(moved + errors)
    return {"moved": moved, "errors": errors}


def remove_duplicates(duplicates: list, progress_cb=None) -> dict:
    removed = 0
    freed = 0
    for dup, _ in duplicates:
        try:
            size = os.path.getsize(dup)
            os.remove(dup)
            removed += 1
            freed += size
        except Exception:
            pass
        if progress_cb:
            progress_cb(removed)
    return {"removed": removed, "freed": freed}


def move_old_files(root: str, old_files: list, exclude: list, progress_cb=None) -> dict:
    archive_dir = os.path.join(root, "Архив")
    os.makedirs(archive_dir, exist_ok=True)
    moved = 0
    for fpath in old_files:
        if is_excluded(fpath, exclude):
            continue
        try:
            fname = os.path.basename(fpath)
            target = os.path.join(archive_dir, fname)
            base, e = os.path.splitext(fname)
            counter = 1
            while os.path.exists(target):
                target = os.path.join(archive_dir, f"{base}_{counter}{e}")
                counter += 1
            shutil.move(fpath, target)
            moved += 1
        except Exception:
            pass
        if progress_cb:
            progress_cb(moved)
    return {"moved": moved}


def rename_files(root: str, categories: dict, exclude: list, progress_cb=None) -> dict:
    renamed = 0
    counters = {}
    for dirpath, _, filenames in os.walk(root):
        if is_excluded(dirpath, exclude):
            continue
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            if is_excluded(fpath, exclude):
                continue
            try:
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
            except Exception:
                continue
            ext = os.path.splitext(fname)[1].lower()
            cat = get_category(ext, categories)
            key = (dirpath, cat)
            counters.setdefault(key, 0)
            counters[key] += 1
            new_name = f"{mtime.strftime('%Y-%m-%d')}_{cat}_{counters[key]:03d}{ext}"
            new_path = os.path.join(dirpath, new_name)
            if os.path.abspath(fpath) == os.path.abspath(new_path):
                continue
            try:
                if os.path.exists(new_path):
                    continue
                os.rename(fpath, new_path)
                renamed += 1
            except Exception:
                pass
            if progress_cb:
                progress_cb(renamed)
    return {"renamed": renamed}


def export_report(stats: dict, path: str, fmt: str = "txt"):
    """Экспорт отчёта в TXT или CSV"""
    if fmt == "csv":
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["Категория", "Количество", "Размер (байт)"])
            for cat, data in sorted(stats["by_category"].items()):
                writer.writerow([cat, data["count"], data["size"]])
            writer.writerow([])
            writer.writerow(["Дубликаты", len(stats["duplicates"])])
            writer.writerow(["Старые файлы (>180 дней)", len(stats["old_files"])])
            writer.writerow(["Всего файлов", stats["total_files"]])
            writer.writerow(["Общий размер (байт)", stats["total_size"]])
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write("=== ОТЧЁТ FolderCleaner ===\n")
            f.write(f"Дата: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write(f"Всего файлов: {stats['total_files']}\n")
            f.write(f"Общий размер: {human_size(stats['total_size'])}\n\n")
            f.write("По категориям:\n")
            for cat, data in sorted(stats["by_category"].items()):
                f.write(f"  {cat}: {data['count']} файлов, {human_size(data['size'])}\n")
            f.write(f"\nДубликатов: {len(stats['duplicates'])}\n")
            f.write(f"Старых файлов (>180 дней): {len(stats['old_files'])}\n")


# ============ GUI ============
class FolderCleanerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("TaxFolder — чистильщик папок")
        self.geometry("1000x780")
        self.minsize(920, 720)

        self.config_data = load_config()
        self.categories = self.config_data["categories"]
        self.exclude = self.config_data["exclude"]
        self.selected_folder = ctk.StringVar(value="")
        self.stats = None
        self.current_theme = load_theme()
        ctk.set_appearance_mode(self.current_theme)

        self.build_ui()

    def build_ui(self):
        # Заголовок
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(
            header, text="🧹 FolderCleaner",
            font=ctk.CTkFont(size=26, weight="bold")
        ).pack(side="left")
        self.theme_btn = ctk.CTkButton(
            header, text="🌙 Тема", width=100, command=self.toggle_theme
        )
        self.theme_btn.pack(side="right", padx=5)
        ctk.CTkButton(
            header, text="⚙️ Настройки", width=120, command=self.open_settings
        ).pack(side="right", padx=5)

        ctk.CTkLabel(
            self, text="Сортировка, дубликаты, архив старых файлов, переименование",
            font=ctk.CTkFont(size=13), text_color="gray"
        ).pack(pady=(0, 10))

        # Папка
        folder_frame = ctk.CTkFrame(self)
        folder_frame.pack(padx=20, pady=5, fill="x")
        ctk.CTkEntry(
            folder_frame, textvariable=self.selected_folder,
            placeholder_text="Путь к папке...", width=600
        ).pack(side="left", padx=10, pady=10)
        ctk.CTkButton(
            folder_frame, text="Выбрать", command=self.choose_folder, width=100
        ).pack(side="left", padx=5, pady=10)
        ctk.CTkButton(
            folder_frame, text="🔍 Сканировать", command=self.scan, width=150,
            fg_color="green"
        ).pack(side="left", padx=5, pady=10)
        ctk.CTkButton(
            folder_frame, text="📄 Экспорт", command=self.export, width=120
        ).pack(side="left", padx=5, pady=10)

        # Вкладки
        self.tabview = ctk.CTkTabview(self, width=960, height=500)
        self.tabview.pack(padx=20, pady=10, fill="both", expand=True)
        self.tabview.add("Обзор")
        self.tabview.add("Дубликаты")
        self.tabview.add("Старые файлы")
        self.tabview.add("Действия")
        self.tabview.add("Исключения")

        self.build_overview_tab()
        self.build_duplicates_tab()
        self.build_old_tab()
        self.build_actions_tab()
        self.build_exclude_tab()

        self.progress = ctk.CTkProgressBar(self, width=920)
        self.progress.pack(pady=(10, 5))
        self.progress.set(0)
        self.status = ctk.CTkLabel(self, text="Готов к работе", text_color="gray")
        self.status.pack(pady=(0, 10))

    def toggle_theme(self):
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        ctk.set_appearance_mode(self.current_theme)
        save_theme(self.current_theme)
        self.theme_btn.configure(
            text="☀️ Тема" if self.current_theme == "dark" else "🌙 Тема"
        )

    def open_settings(self):
        win = ctk.CTkToplevel(self)
        win.title("Настройки категорий")
        win.geometry("600x600")
        ctk.CTkLabel(
            win, text="Редактор категорий (JSON)",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)
        textbox = ctk.CTkTextbox(win, width=560, height=450)
        textbox.pack(padx=20, pady=10)
        textbox.insert("1.0", json.dumps(self.categories, ensure_ascii=False, indent=2))

        def save():
            try:
                new_cfg = json.loads(textbox.get("1.0", "end"))
                self.categories = new_cfg
                self.config_data["categories"] = new_cfg
                save_config(self.config_data)
                messagebox.showinfo("Готово", "Категории сохранены. Пересканируй папку.")
                win.destroy()
            except Exception as e:
                messagebox.showerror("Ошибка", f"Некорректный JSON:\n{e}")

        ctk.CTkButton(win, text="💾 Сохранить", command=save, width=200).pack(pady=10)

    def choose_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.selected_folder.set(path)
            self.set_status(f"Папка: {path}", "gray")

    def set_status(self, text, color="gray"):
        self.status.configure(text=text, text_color=color)

    # ---------- ОБЗОР ----------
    def build_overview_tab(self):
        tab = self.tabview.tab("Обзор")
        self.overview_frame = ctk.CTkScrollableFrame(tab, width=920, height=420)
        self.overview_frame.pack(padx=10, pady=10, fill="both", expand=True)
        ctk.CTkLabel(
            self.overview_frame, text="Нажми «Сканировать», чтобы увидеть статистику",
            text_color="gray"
        ).pack(pady=20)

    def scan(self):
        folder = self.selected_folder.get()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Ошибка", "Выбери папку для сканирования")
            return
        self.set_status("Сканирую папку...", "orange")
        self.progress.set(0)
        threading.Thread(target=self._scan_thread, args=(folder,), daemon=True).start()

    def _scan_thread(self, folder):
        stats = scan_folder(folder, self.categories, self.exclude)
        self.stats = stats
        self.after(0, lambda: self.render_overview(stats))
        self.after(0, lambda: self.render_duplicates(stats))
        self.after(0, lambda: self.render_old(stats))
        self.after(0, lambda: self.progress.set(1))
        self.after(0, lambda: self.set_status("Сканирование завершено", "green"))

    def render_overview(self, stats):
        for w in self.overview_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.overview_frame,
            text=f"📁 Всего файлов: {stats['total_files']}  |  💾 Общий размер: {human_size(stats['total_size'])}",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(pady=10, anchor="w")
        for cat, data in sorted(stats["by_category"].items()):
            row = ctk.CTkFrame(self.overview_frame)
            row.pack(fill="x", pady=3, padx=5)
            ctk.CTkLabel(row, text=f"  {cat}", width=200, anchor="w",
                         font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
            ctk.CTkLabel(row, text=f"{data['count']} файлов", width=150, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=human_size(data["size"]), width=150, anchor="w",
                         text_color="gray").pack(side="left")
        ctk.CTkLabel(
            self.overview_frame,
            text=f"♻️ Дубликатов: {len(stats['duplicates'])}  |  ⏳ Старых (>180 дней): {len(stats['old_files'])}",
            font=ctk.CTkFont(size=13), text_color="orange"
        ).pack(pady=15, anchor="w")

    # ---------- ДУБЛИКАТЫ ----------
    def build_duplicates_tab(self):
        tab = self.tabview.tab("Дубликаты")
        ctk.CTkLabel(tab, text="Дубликаты файлов (по MD5-хешу)",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=10)
        self.dup_frame = ctk.CTkScrollableFrame(tab, width=900, height=300)
        self.dup_frame.pack(padx=10, pady=5, fill="both", expand=True)
        ctk.CTkButton(tab, text="🗑️ Удалить все дубликаты (оставить первый)",
                      command=self.delete_duplicates, fg_color="darkred", width=400).pack(pady=8)

    def render_duplicates(self, stats):
        for w in self.dup_frame.winfo_children():
            w.destroy()
        if not stats["duplicates"]:
            ctk.CTkLabel(self.dup_frame, text="Дубликатов не найдено ✅").pack(pady=10)
            return
        for i, (dup, original) in enumerate(stats["duplicates"], 1):
            row = ctk.CTkFrame(self.dup_frame)
            row.pack(fill="x", pady=2, padx=5)
            ctk.CTkLabel(row, text=f"{i}. {os.path.basename(dup)}", width=350, anchor="w",
                         font=ctk.CTkFont(size=12)).pack(side="left")
            ctk.CTkLabel(row, text=f"оригинал: {os.path.basename(original)}",
                         text_color="gray", font=ctk.CTkFont(size=11)).pack(side="left", padx=10)

    def delete_duplicates(self):
        if not self.stats or not self.stats["duplicates"]:
            messagebox.showinfo("Инфо", "Сначала просканируй папку")
            return
        if not messagebox.askyesno("Подтверждение",
                                   f"Удалить {len(self.stats['duplicates'])} дубликатов?\n"
                                   "Оригиналы останутся на месте."):
            return
        self.set_status("Удаляю дубликаты...", "orange")
        self.progress.set(0)
        threading.Thread(target=self._delete_dups_thread, daemon=True).start()

    def _delete_dups_thread(self):
        total = len(self.stats["duplicates"])
        def cb(n):
            self.after(0, lambda: self.progress.set(n / total))
        result = remove_duplicates(self.stats["duplicates"], progress_cb=cb)
        self.after(0, lambda: self.set_status(
            f"Удалено {result['removed']} дубликатов, освобождено {human_size(result['freed'])}",
            "green"))
        self.after(0, lambda: messagebox.showinfo(
            "Готово", f"Удалено: {result['removed']}\nОсвобождено: {human_size(result['freed'])}"))
        self.after(0, self.scan)

    # ---------- СТАРЫЕ ----------
    def build_old_tab(self):
        tab = self.tabview.tab("Старые файлы")
        ctk.CTkLabel(tab, text="Файлы, которые не трогали больше 180 дней",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=10)
        self.old_frame = ctk.CTkScrollableFrame(tab, width=900, height=300)
        self.old_frame.pack(padx=10, pady=5, fill="both", expand=True)
        ctk.CTkButton(tab, text="📦 Переместить в папку «Архив»",
                      command=self.move_old, fg_color="orange", width=400).pack(pady=8)

    def render_old(self, stats):
        for w in self.old_frame.winfo_children():
            w.destroy()
        if not stats["old_files"]:
            ctk.CTkLabel(self.old_frame, text="Старых файлов нет ✅").pack(pady=10)
            return
        for i, fpath in enumerate(stats["old_files"][:200], 1):
            ctk.CTkLabel(self.old_frame, text=f"{i}. {fpath}", anchor="w",
                         font=ctk.CTkFont(size=11)).pack(fill="x", pady=1, padx=5)
        if len(stats["old_files"]) > 200:
            ctk.CTkLabel(self.old_frame, text=f"... и ещё {len(stats['old_files']) - 200}",
                         text_color="gray").pack()

    def move_old(self):
        if not self.stats or not self.stats["old_files"]:
            messagebox.showinfo("Инфо", "Сначала просканируй папку")
            return
        if not messagebox.askyesno("Подтверждение",
                                   f"Переместить {len(self.stats['old_files'])} файлов в папку «Архив»?"):
            return
        folder = self.selected_folder.get()
        total = len(self.stats["old_files"])
        def cb(n):
            self.after(0, lambda: self.progress.set(n / total))
        result = move_old_files(folder, self.stats["old_files"], self.exclude, progress_cb=cb)
        self.set_status(f"Перемещено {result['moved']} старых файлов", "green")
        messagebox.showinfo("Готово", f"Перемещено: {result['moved']}")
        self.scan()

    # ---------- ДЕЙСТВИЯ ----------
    def build_actions_tab(self):
        tab = self.tabview.tab("Действия")
        ctk.CTkLabel(tab, text="Массовые операции с файлами",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=15)
        ctk.CTkButton(tab, text="📂 Отсортировать файлы по категориям",
                      command=self.do_sort, width=450, height=45).pack(pady=10)
        ctk.CTkButton(tab, text="✏️ Переименовать по шаблону (дата_категория_номер)",
                      command=self.do_rename, width=450, height=45).pack(pady=10)
        ctk.CTkLabel(tab, text="⚠️ Перед массовыми операциями сделай бэкап папки.\n"
                               "Переименование затронет все файлы в папке и подпапках.",
                     text_color="orange", font=ctk.CTkFont(size=12)).pack(pady=25)

    def do_sort(self):
        folder = self.selected_folder.get()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Ошибка", "Выбери папку")
            return
        if not messagebox.askyesno("Подтверждение",
                                   "Отсортировать все файлы по категориям?\n"
                                   "Файлы будут перемещены в подпапки."):
            return
        self.set_status("Сортирую файлы...", "orange")
        self.progress.set(0)
        threading.Thread(target=self._sort_thread, args=(folder,), daemon=True).start()

    def _sort_thread(self, folder):
        total = self.stats["total_files"] if self.stats else 1
        def cb(n):
            self.after(0, lambda: self.progress.set(min(n / max(total, 1), 1)))
        result = sort_files(folder, self.categories, self.exclude, progress_cb=cb)
        self.after(0, lambda: self.set_status(
            f"Перемещено: {result['moved']} | Ошибок: {result['errors']}", "green"))
        self.after(0, lambda: messagebox.showinfo(
            "Готово", f"Перемещено файлов: {result['moved']}\nОшибок: {result['errors']}"))
        self.after(0, self.scan)

    def do_rename(self):
        folder = self.selected_folder.get()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Ошибка", "Выбери папку")
            return
        if not messagebox.askyesno("Подтверждение",
                                   "Переименовать все файлы по шаблону?\n"
                                   "Пример: 2023-05-01_Фото_001.jpg\n\n"
                                   "Это необратимо без бэкапа!"):
            return
        self.set_status("Переименовываю...", "orange")
        threading.Thread(target=self._rename_thread, args=(folder,), daemon=True).start()

    def _rename_thread(self, folder):
        result = rename_files(folder, self.categories, self.exclude)
        self.after(0, lambda: self.set_status(f"Переименовано: {result['renamed']}", "green"))
        self.after(0, lambda: messagebox.showinfo(
            "Готово", f"Переименовано файлов: {result['renamed']}"))
        self.after(0, self.scan)

    # ---------- ИСКЛЮЧЕНИЯ ----------
    def build_exclude_tab(self):
        tab = self.tabview.tab("Исключения")
        ctk.CTkLabel(tab, text="Папки и файлы, которые программа не трогает",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=10)
        self.exclude_frame = ctk.CTkScrollableFrame(tab, width=900, height=300)
        self.exclude_frame.pack(padx=10, pady=5, fill="both", expand=True)
        self.render_exclude()

        add_frame = ctk.CTkFrame(tab)
        add_frame.pack(pady=10, fill="x", padx=10)
        self.exclude_entry = ctk.CTkEntry(add_frame, placeholder_text="Название папки/файла...", width=400)
        self.exclude_entry.pack(side="left", padx=10, pady=10)
        ctk.CTkButton(add_frame, text="➕ Добавить", command=self.add_exclude, width=120).pack(side="left", padx=5)
        ctk.CTkButton(add_frame, text="💾 Сохранить", command=self.save_exclude, width=120,
                      fg_color="green").pack(side="left", padx=5)

    def render_exclude(self):
        for w in self.exclude_frame.winfo_children():
            w.destroy()
        if not self.exclude:
            ctk.CTkLabel(self.exclude_frame, text="Исключений нет").pack(pady=10)
            return
        for i, ex in enumerate(self.exclude, 1):
            row = ctk.CTkFrame(self.exclude_frame)
            row.pack(fill="x", pady=2, padx=5)
            ctk.CTkLabel(row, text=f"{i}. {ex}", anchor="w", width=700).pack(side="left", padx=5)
            ctk.CTkButton(row, text="❌", width=40, fg_color="darkred",
                          command=lambda e=ex: self.remove_exclude(e)).pack(side="right", padx=5)

    def add_exclude(self):
        value = self.exclude_entry.get().strip()
        if value and value not in self.exclude:
            self.exclude.append(value)
            self.config_data["exclude"] = self.exclude
            save_config(self.config_data)
            self.render_exclude()
            self.exclude_entry.delete(0, "end")

    def remove_exclude(self, value):
        if value in self.exclude:
            self.exclude.remove(value)
            self.config_data["exclude"] = self.exclude
            save_config(self.config_data)
            self.render_exclude()

    def save_exclude(self):
        self.config_data["exclude"] = self.exclude
        save_config(self.config_data)
        messagebox.showinfo("Готово", "Исключения сохранены")

    # ---------- ЭКСПОРТ ----------
    def export(self):
        if not self.stats:
            messagebox.showinfo("Инфо", "Сначала просканируй папку")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("CSV", "*.csv")],
            initialfile=f"report_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        )
        if not path:
            return
        fmt = "csv" if path.lower().endswith(".csv") else "txt"
        try:
            export_report(self.stats, path, fmt)
            messagebox.showinfo("Готово", f"Отчёт сохранён:\n{path}")
            self.set_status(f"Отчёт экспортирован: {os.path.basename(path)}", "green")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить отчёт:\n{e}")


if __name__ == "__main__":
    try:
        app = FolderCleanerApp()
        app.after(200, lambda: app.iconbitmap("icon.ico"))
        app.mainloop()
    except Exception as e:
        print(f"Ошибка запуска: {e}")
        input("Нажми Enter...")