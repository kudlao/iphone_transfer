"""Hush Photo - Windows local photo exporter; original source files are read-only."""
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import io
import queue
import shutil
import threading
import time
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageOps, ImageCms
from pillow_heif import register_heif_opener

register_heif_opener()
IMAGE_EXTS = {'.heic', '.heif', '.jpg', '.jpeg', '.png', '.tif', '.tiff'}
HEIC_EXTS = {'.heic', '.heif'}
VIDEO_EXTS = {'.mov', '.mp4'}


@dataclass(frozen=True)
class ExportOptions:
    mode: str  # both | original | jpeg | tiff
    quality: int = 97
    copy_mov: bool = True


def unique_path(destination: Path) -> Path:
    if not destination.exists():
        return destination
    index = 2
    while True:
        candidate = destination.with_name(f'{destination.stem} ({index}){destination.suffix}')
        if not candidate.exists():
            return candidate
        index += 1


def prepare_image(source: Path):
    with Image.open(source) as raw:
        exif = raw.getexif()
        image = ImageOps.exif_transpose(raw)
        exif[274] = 1
        icc = image.info.get('icc_profile') or raw.info.get('icc_profile')
        # Convert ordinary ICC images to sRGB. HDR tone mapping is not implemented.
        if icc:
            try:
                source_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
                target_profile = ImageCms.createProfile('sRGB')
                image = ImageCms.profileToProfile(image.convert('RGB'), source_profile, target_profile, outputMode='RGB')
                icc = ImageCms.ImageCmsProfile(target_profile).tobytes()
            except Exception:
                # Avoid attaching a potentially misleading source ICC to unconverted RGB.
                image = image.convert('RGB')
                icc = None
        else:
            image = image.convert('RGB')
        image.load()
        return image, exif.tobytes(), icc


def convert_image(source: Path, dest: Path, kind: str, quality: int):
    image, exif, icc = prepare_image(source)
    if kind == 'jpeg':
        params = dict(format='JPEG', quality=quality, subsampling=0, optimize=True, exif=exif)
        if icc:
            params['icc_profile'] = icc
        image.save(dest, **params)
    else:
        # Lossless pixel representation; conversion cannot restore lost HEIC detail/HDR.
        params = dict(format='TIFF', compression='tiff_lzw', tiffinfo=None)
        image.save(dest, **params)
    with Image.open(dest) as verify:
        verify.verify()


def export_directory(source_dir: Path, dest_dir: Path, options: ExportOptions, reporter, cancel_event=None, selected_paths=None, folder_mode='original'):
    pictures = sorted(p for p in source_dir.rglob('*') if p.is_file() and p.suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS) and (selected_paths is None or p in selected_paths))
    failures = []
    processed = 0
    copied_mov = set()
    cancelled = False
    reporter(0, len(pictures), 'Подготовка к экспорту…')
    for index, source in enumerate(pictures, 1):
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            break
        reporter(index - 1, len(pictures), f'Обработка: {source.name}')
        rel = source.relative_to(source_dir)
        if folder_mode == 'flat':
            folder = dest_dir
        elif folder_mode == 'year-month':
            from safe_export import capture_datetime
            dt = capture_datetime(source)
            folder = dest_dir / (dt.strftime('%Y-%m') if dt else 'Без даты')
        else:
            folder = dest_dir / rel.parent
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if source.suffix.lower() in VIDEO_EXTS:
                # Videos are copied byte-for-byte, regardless of the photo conversion mode.
                shutil.copy2(source, unique_path(folder / source.name))
                processed += 1
                reporter(index, len(pictures), source.name)
                continue
            if options.mode in {'both', 'original'}:
                shutil.copy2(source, unique_path(folder / source.name))
            if options.mode in {'both', 'jpeg', 'tiff'}:
                extension = '.jpg' if options.mode != 'tiff' else '.tiff'
                kind = 'jpeg' if options.mode != 'tiff' else 'tiff'
                # Never recompress an existing JPEG; for 'both' the original IS its JPEG.
                already_copied = options.mode == 'both' and source.suffix.lower() in {'.jpg', '.jpeg'}
                if not already_copied:
                    destination = unique_path(folder / (source.stem + extension))
                    if kind == 'jpeg' and source.suffix.lower() in {'.jpg', '.jpeg'}:
                        shutil.copy2(source, destination)
                    else:
                        convert_image(source, destination, kind, options.quality)
            if options.copy_mov:
                for movie in source.parent.iterdir():
                    if movie.is_file() and movie.suffix.lower() == '.mov' and movie.stem.casefold() == source.stem.casefold():
                        if movie not in copied_mov:
                            shutil.copy2(movie, unique_path(folder / movie.name))
                            copied_mov.add(movie)
            processed += 1
        except Exception as exc:
            failures.append(f'{source}: {exc}')
        reporter(index, len(pictures), source.name)
    report = unique_path(dest_dir / 'export_report.txt')
    report.write_text(f'Export: {datetime.now().isoformat(timespec="seconds")}\nMode: {options.mode}\nJPEG quality: {options.quality}\nCopy MOV: {options.copy_mov}\nFiles processed: {processed}/{len(pictures)}\nCancelled: {cancelled}\nFailures: {len(failures)}\n' + '\n'.join(failures), encoding='utf-8')
    return processed, len(pictures), failures, cancelled


class OptionsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title('Параметры экспорта фотографий')
        self.geometry('550x390')
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self.mode = tk.StringVar(value='both')
        self.quality = tk.IntVar(value=97)
        self.mov = tk.BooleanVar(value=True)
        container = ttk.Frame(self, padding=18)
        container.pack(fill='both', expand=True)
        ttk.Label(container, text='Выбери формат перед экспортом', font=('Segoe UI', 15, 'bold')).pack(anchor='w', pady=(0, 12))
        variants = (
            ('both', 'HEIC + JPEG — оригинал и качественная копия (рекомендуется)'),
            ('original', 'Только оригиналы — без перекодирования и потерь'),
            ('jpeg', 'Только JPEG — удобство просмотра в Windows'),
            ('tiff', 'TIFF — большой файл без дополнительных потерь пикселей'),
        )
        for key, caption in variants:
            ttk.Radiobutton(container, text=caption, value=key, variable=self.mode).pack(anchor='w', pady=5)
        row = ttk.Frame(container)
        row.pack(fill='x', pady=(16, 6))
        ttk.Label(row, text='Качество JPEG (85–100):').pack(side='left')
        self.spin = ttk.Spinbox(row, from_=85, to=100, width=5, textvariable=self.quality)
        self.spin.pack(side='left', padx=12)
        ttk.Checkbutton(container, text='Сохранять MOV — движение Live Photo', variable=self.mov).pack(anchor='w', pady=8)
        ttk.Label(container, text='Оригинальные файлы в исходной папке никогда не удаляются.\nJPEG не сохраняет анимацию и может отличаться по HDR.', foreground='#666666').pack(anchor='w', pady=6)
        buttons = ttk.Frame(container)
        buttons.pack(fill='x', side='bottom', pady=(12, 0))
        ttk.Button(buttons, text='Отмена', command=self.destroy).pack(side='right', padx=(10, 0))
        ttk.Button(buttons, text='Начать экспорт', command=self.confirm).pack(side='right')
        self.mode.trace_add('write', self.update_quality)
        self.update_quality()
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.wait_visibility()
        self.focus_set()

    def update_quality(self, *_):
        self.spin.configure(state='normal' if self.mode.get() in {'both', 'jpeg'} else 'disabled')

    def confirm(self):
        try:
            quality = int(self.quality.get())
            if not 85 <= quality <= 100:
                raise ValueError()
        except (ValueError, tk.TclError):
            messagebox.showerror('Некорректное качество', 'Введите качество JPEG от 85 до 100.', parent=self)
            return
        self.result = ExportOptions(self.mode.get(), quality, self.mov.get())
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Hush Photo — Windows (прототип)')
        self.geometry('850x510')
        self.minsize(690, 370)
        self.cancel_event = threading.Event()
        self.running = False
        self.usb = tk.BooleanVar(value=False)
        self.src = tk.StringVar()
        self.dest = tk.StringVar()
        self.events = queue.Queue()
        pad = {'padx': 14, 'pady': 8}
        ttk.Label(self, text='Экспорт фото и Live Photos с выбором формата', font=('Segoe UI', 16, 'bold')).pack(anchor='w', **pad)
        ttk.Checkbutton(self, text='Импортировать напрямую с подключённого iPhone по USB (DCIM)', variable=self.usb).pack(anchor='w', padx=14, pady=5)
        for label, variable in [('Локальная папка (если без USB)', self.src), ('Папка для экспорта', self.dest)]:
            row = ttk.Frame(self)
            row.pack(fill='x', **pad)
            ttk.Label(row, text=label, width=28).pack(side='left')
            ttk.Entry(row, textvariable=variable).pack(side='left', fill='x', expand=True, padx=6)
            ttk.Button(row, text='Выбрать…', command=lambda v=variable: self.choose(v)).pack(side='right')
        self.go = ttk.Button(self, text='Выбрать параметры и экспортировать…', command=self.start)
        self.go.pack(anchor='w', **pad)
        progress_frame = ttk.Frame(self)
        progress_frame.pack(fill='x', padx=14, pady=(3, 0))
        self.progress_count = tk.StringVar(value='0 / 0 фотографий (0%)')
        self.rate_label = tk.StringVar(value='Скорость: —  |  Осталось: —')
        self.current_file = tk.StringVar(value='Текущий файл: —')
        self.progress_started = 0.0
        self.last_measure = None
        self.smoothed_rate = None
        self.last_usb_update = 0
        ttk.Label(progress_frame, textvariable=self.progress_count).pack(side='left')
        self.cancel_button = ttk.Button(progress_frame, text='Отменить экспорт', command=self.cancel, state='disabled')
        self.cancel_button.pack(side='right')
        self.progress = ttk.Progressbar(self, mode='determinate', maximum=100)
        self.progress.pack(fill='x', padx=14, pady=(7, 4))
        ttk.Label(self, textvariable=self.current_file).pack(anchor='w', padx=14, pady=3)
        ttk.Label(self, textvariable=self.rate_label).pack(anchor='w', padx=14, pady=3)
        self.status = tk.StringVar(value='Сначала скопируй оригинальные HEIC и MOV с iPhone в папку на Windows.')
        ttk.Label(self, textvariable=self.status, wraplength=740).pack(anchor='w', **pad)
        ttk.Label(self, text='USB: требуется Apple Devices и доверие к ПК. Из iCloud доступны только загруженные на телефон оригиналы.', foreground='#666666').pack(anchor='w', **pad)
        self.after(150, self.poll)

    def choose(self, variable):
        selection = filedialog.askdirectory()
        if selection:
            variable.set(selection)

    def start(self):
        if (not self.usb.get() and not self.src.get()) or not self.dest.get():
            messagebox.showerror('Ошибка', 'Укажи папку экспорта и источник.')
            return
        usb_mode = self.usb.get()
        source, dest = Path(self.src.get() or '.'), Path(self.dest.get())
        if not usb_mode and not source.is_dir():
            messagebox.showerror('Ошибка', 'Исходная папка не найдена.')
            return
        if not usb_mode and (source.resolve() == dest.resolve() or source.resolve() in dest.resolve().parents or dest.resolve() in source.resolve().parents):
            messagebox.showerror('Ошибка', 'Выбери две отдельные папки, не вложенные друг в друга.')
            return
        dialog = OptionsDialog(self)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        options = dialog.result
        self.go.configure(state='disabled')
        self.cancel_event.clear()
        self.running = True
        self.cancel_button.configure(state='normal')
        self.progress.configure(value=0)
        self.progress_count.set('0 / 0 фотографий (0%)')
        self.rate_label.set('Скорость: —  |  Осталось: —')
        self.current_file.set('Текущий файл: —')
        self.last_measure = None
        self.smoothed_rate = None
        self.progress_started = time.monotonic()
        def work():
            try:
                dest.mkdir(parents=True, exist_ok=True)
                if usb_mode:
                    from iphone_usb import copy_from_iphone
                    with tempfile.TemporaryDirectory(prefix='hush_iphone_') as temp:
                        stage = Path(temp)
                        usb_result = copy_from_iphone(stage, lambda b,t,f,n,all_n: self.events.put(('usb', (b,t,f,n,all_n))), self.cancel_event)
                        if usb_result[2]:
                            (dest / 'usb_import_errors.txt').write_text('\n'.join(usb_result[2]), encoding='utf-8')
                        if self.cancel_event.is_set():
                            self.events.put(('done', (usb_result[0], usb_result[1], usb_result[2], True)))
                            return
                        self.events.put(('phase', 'USB-копирование завершено. Создание фотографий в выбранном формате…'))
                        result = export_directory(stage, dest, options, lambda n,total,name: self.events.put(('progress', (n,total,name))), self.cancel_event)
                else:
                    result = export_directory(source, dest, options, lambda n, total, name: self.events.put(('progress', (n, total, name))), self.cancel_event)
                self.events.put(('done', result))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def cancel(self):
        if self.running:
            self.cancel_event.set()
            self.cancel_button.configure(state='disabled')
            self.status.set('Отмена запрошена: текущий файл будет завершён, затем экспорт остановится…')

    def finish(self):
        self.running = False
        self.go.configure(state='normal')
        self.cancel_button.configure(state='disabled')

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == 'phase':
                self.status.set(value)
                self.last_measure = None
                self.smoothed_rate = None
            elif kind == 'usb':
                b,total,name,n,all_n = value
                now = time.monotonic()
                if self.last_measure and now > self.last_measure[0] and b >= self.last_measure[1]:
                    instantaneous = (b-self.last_measure[1])/(now-self.last_measure[0])
                    self.smoothed_rate = instantaneous if self.smoothed_rate is None else (0.2*instantaneous + 0.8*self.smoothed_rate)
                if not self.last_measure or now-self.last_measure[0] >= 0.8:
                    self.last_measure = (now,b)
                rate = self.smoothed_rate or 0
                eta = int((total-b)/rate) if rate > 1024 and total else None
                eta_text = f'{eta//3600:02}:{eta//60%60:02}:{eta%60:02}' if eta is not None else '—'
                self.rate_label.set(f'USB: {rate/1048576:.1f} МБ/с  |  Осталось: {eta_text}  |  {b/1048576:.1f} / {total/1048576:.1f} МБ')
                self.progress.configure(value=100*b/total if total else 0)
                self.progress_count.set(f'{n} / {all_n} файлов ({100*b/total:.0f}% данных)' if total else f'{n} / {all_n} файлов')
                self.current_file.set(f'Текущий файл: {name}')
            elif kind == 'progress':
                n, total, name = value
                percent = round(100 * n / total) if total else 100
                self.progress.configure(value=percent)
                self.progress_count.set(f'{n} / {total} фотографий ({percent}%)')
                self.current_file.set(f'Текущий файл: {name}')
                elapsed = time.monotonic()-self.progress_started
                # For local conversion these are file counts, not bytes.
                if n and elapsed > 0 and self.last_measure is None:
                    self.last_measure = (time.monotonic(), n)
                elif self.last_measure and time.monotonic()-self.last_measure[0]>0.8:
                    dt = time.monotonic()-self.last_measure[0]
                    r = max(0,(n-self.last_measure[1])/dt)
                    self.smoothed_rate = r if self.smoothed_rate is None else .3*r+.7*self.smoothed_rate
                    self.last_measure = (time.monotonic(),n)
                rate = self.smoothed_rate or 0
                eta = (total-n)/rate if rate>0 else None
                self.rate_label.set(f'Обработка: {rate:.1f} фото/с  |  Осталось: {int(eta)//60}м {int(eta)%60}с' if eta is not None else 'Обработка: расчёт времени…')
                if not self.cancel_event.is_set():
                    self.status.set(name)
            elif kind == 'done':
                done, total, failures, cancelled = value
                self.status.set(f'{"Отменено" if cancelled else "Готово"}: {done}/{total} успешно. Ошибок: {len(failures)}. Отчёт: export_report.txt')
                self.finish()
                messagebox.showinfo('Экспорт остановлен' if cancelled else 'Завершено', self.status.get())
            elif kind == 'error':
                self.status.set(f'Ошибка: {value}')
                self.finish()
                messagebox.showerror('Ошибка', value)
        self.after(150, self.poll)


if __name__ == '__main__':
    App().mainloop()
