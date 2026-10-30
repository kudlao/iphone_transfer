"""Hush Photo modern Windows interface. Local preview + experimental USB importer."""
import queue
import threading
import tempfile
import shutil
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from main import IMAGE_EXTS, VIDEO_EXTS, ExportOptions, export_directory
from media_groups import group_suffixes, matches_video_filter, video_category, photo_pair_index

register_heif_opener()
ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('blue')
BG='#10131b'; PANEL='#1a2030'; ALT='#242c3e'; FG='#f3f6ff'; MUTED='#a6afc2'; ACC='#6786ef'

class Settings(ctk.CTkToplevel):
    def __init__(self, parent, video=False):
        super().__init__(parent)
        self.title('Настройки экспорта видео' if video else 'Настройки экспорта'); self.geometry('540x610'); self.resizable(False,False)
        self.result=None; self.mode=tk.StringVar(value='both'); self.quality=tk.IntVar(value=97); self.mov=tk.BooleanVar(value=True); self.folders=tk.StringVar(value='Оригинальная структура')
        self.configure(fg_color=BG)
        if video:
            self.geometry('540x270')
            ctk.CTkLabel(self,text='Экспорт видео',font=('Segoe UI',23,'bold')).pack(anchor='w',padx=26,pady=(24,9))
            ctk.CTkLabel(self,text='MOV и MP4 копируются без перекодирования, с исходным качеством.',text_color=MUTED,wraplength=470).pack(anchor='w',padx=26,pady=(4,14))
            ctk.CTkOptionMenu(self,values=['Оригинальная структура','По годам и месяцам (2026-10)','Без разделения на папки'],variable=self.folders).pack(fill='x',padx=27,pady=(8,8))
            ctk.CTkButton(self,text='Начать экспорт видео',height=42,command=self.confirm_video).pack(fill='x',padx=27,pady=(12,12))
            self.transient(parent); self.grab_set(); self.focus_set()
            return
        ctk.CTkLabel(self,text='Параметры экспорта',font=('Segoe UI',23,'bold')).pack(anchor='w',padx=26,pady=(24,9))
        ctk.CTkLabel(self,text='Формат фотографий',text_color=MUTED).pack(anchor='w',padx=26,pady=(10,5))
        for value,label in [('both','Оригинал + JPEG — рекомендуется'),('original','Только оригиналы'),('jpeg','Только JPEG'),('tiff','TIFF — без дополнительного сжатия с потерями')]:
            ctk.CTkRadioButton(self,text=label,variable=self.mode,value=value).pack(anchor='w',padx=27,pady=8)
        self.qLabel=ctk.CTkLabel(self,text='Качество JPEG: 97'); self.qLabel.pack(anchor='w',padx=26,pady=(12,0))
        self.slider=ctk.CTkSlider(self,from_=85,to=100,number_of_steps=15,command=self.change_q); self.slider.set(97); self.slider.pack(fill='x',padx=27,pady=10)
        ctk.CTkCheckBox(self,text='Сохранять MOV от Live Photos',variable=self.mov).pack(anchor='w',padx=27,pady=9)
        ctk.CTkLabel(self,text='Оригиналы сохраняются; JPEG — SDR-копия, HDR не гарантирован.',text_color=MUTED,wraplength=475).pack(anchor='w',padx=27,pady=(8,15))
        ctk.CTkOptionMenu(self,values=['Оригинальная структура','По годам и месяцам (2026-10)','Без разделения на папки'],variable=self.folders).pack(fill='x',padx=27,pady=(8,6))
        ctk.CTkButton(self,text='Начать экспорт',height=42,command=self.confirm).pack(fill='x',padx=27,pady=(6,12))
        self.transient(parent); self.grab_set(); self.focus_set()
    def confirm_video(self):
        self.result=ExportOptions('original',97,False)
        self.result_folders=('year-month' if self.folders.get().startswith('По годам') else 'flat' if self.folders.get().startswith('Без разделения') else 'original')
        self.destroy()

    def change_q(self, v):
        self.quality.set(int(round(v))); self.qLabel.configure(text=f'Качество JPEG: {self.quality.get()}')
    def confirm(self):
        self.result=ExportOptions(self.mode.get(),self.quality.get(),self.mov.get()); self.result_folders=('year-month' if self.folders.get().startswith('По годам') else 'flat' if self.folders.get().startswith('Без разделения') else 'original'); self.destroy()

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('Hush Photo · Windows'); self.geometry('1170x780'); self.minsize(900,620); self.configure(fg_color=BG)
        self.source=tk.StringVar(); self.target=tk.StringVar(); self.usb=tk.BooleanVar(value=False)
        self.group=tk.StringVar(value='Фото'); self.video_filter=tk.StringVar(value='Все видео'); self.photo_index=set(); self.entries=[]; self.selected=set(); self.usb_items=[]; self.usb_preview={}; self.preview_cache=Path(__import__('os').environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'HushPhoto' / 'previews'; self.thumbnails=[]; self.events=queue.Queue(); self.cancel_event=threading.Event(); self.running=False
        from preview_cache import clear_legacy_cache, trim_cache
        clear_legacy_cache(self.preview_cache)
        trim_cache(self.preview_cache)
        self.last_sample=None; self.speed=None; self.scan_token=0; self.start_clock=0; self.scan_cancel=threading.Event(); self.usb_scanning=False; self.usb_draw_at=0; self.preview_offset=0; self.preview_loading=False
        self.sidebar=ctk.CTkFrame(self,width=245,fg_color=PANEL,corner_radius=0); self.sidebar.pack(side='left',fill='y'); self.sidebar.pack_propagate(False)
        ctk.CTkLabel(self.sidebar,text='HUSH  PHOTO',font=('Segoe UI',24,'bold'),text_color=FG).pack(anchor='w',padx=23,pady=(26,7))
        ctk.CTkLabel(self.sidebar,text='Перенос фото и видео с iPhone',text_color=MUTED,font=('Segoe UI',12)).pack(anchor='w',padx=23)
        ctk.CTkLabel(self.sidebar,text='ИСТОЧНИК',text_color=MUTED,font=('Segoe UI',11,'bold')).pack(anchor='w',padx=23,pady=(37,11))
        ctk.CTkRadioButton(self.sidebar,text='Папка на компьютере',variable=self.usb,value=False,command=self.source_changed).pack(anchor='w',padx=20,pady=11)
        ctk.CTkRadioButton(self.sidebar,text='iPhone по USB',variable=self.usb,value=True,command=self.source_changed).pack(anchor='w',padx=20,pady=11)
        self.select_source=ctk.CTkButton(self.sidebar,text='Выбрать папку…',fg_color=ALT,hover_color='#36415b',command=self.choose_source); self.select_source.pack(fill='x',padx=19,pady=(18,7))
        self.source_name=ctk.CTkLabel(self.sidebar,text='Папка не выбрана',text_color=MUTED,wraplength=200); self.source_name.pack(padx=19,anchor='w')
        ctk.CTkFrame(self.sidebar,height=2,fg_color=ALT).pack(fill='x',padx=18,pady=27)
        ctk.CTkLabel(self.sidebar,text='НАЗНАЧЕНИЕ',text_color=MUTED,font=('Segoe UI',11,'bold')).pack(anchor='w',padx=23,pady=(0,10))
        ctk.CTkButton(self.sidebar,text='Куда сохранять…',fg_color=ALT,hover_color='#36415b',command=self.choose_target).pack(fill='x',padx=19,pady=6)
        self.target_name=ctk.CTkLabel(self.sidebar,text='Папка не выбрана',text_color=MUTED,wraplength=200); self.target_name.pack(padx=19,anchor='w',pady=4)
        ctk.CTkLabel(self.sidebar,text='USB-доступ экспериментальный.\nРазблокируй iPhone и нажми «Доверять».',text_color=MUTED,wraplength=205,justify='left').pack(side='bottom',anchor='w',padx=21,pady=25)
        self.body=ctk.CTkFrame(self,fg_color=BG,corner_radius=0); self.body.pack(side='left',fill='both',expand=True,padx=22,pady=19)
        title=ctk.CTkFrame(self.body,fg_color='transparent'); title.pack(fill='x',pady=(0,12))
        ctk.CTkLabel(title,text='Медиатека',font=('Segoe UI',28,'bold')).pack(side='left')
        self.count=ctk.CTkLabel(title,text='0 файлов',text_color=MUTED); self.count.pack(side='left',padx=18)
        ctk.CTkButton(title,text='Обновить',width=100,fg_color=ALT,command=self.refresh).pack(side='right')
        groups=ctk.CTkFrame(self.body,fg_color='transparent'); groups.pack(fill='x',pady=(0,10))
        ctk.CTkSegmentedButton(groups,values=['Фото','Видео'],variable=self.group,command=self.group_changed).pack(side='left')
        self.video_filters=ctk.CTkSegmentedButton(groups,values=['Все видео','Видеоролики','Live Photos'],variable=self.video_filter,command=self.video_filter_changed)
        self.video_filters.pack(side='left',padx=(12,0)); self.video_filters.pack_forget()
        toolbar=ctk.CTkFrame(self.body,fg_color='transparent'); toolbar.pack(fill='x',pady=(0,12))
        self.search=ctk.CTkEntry(toolbar,placeholder_text='Поиск по имени файла',height=38); self.search.pack(side='left',fill='x',expand=True,padx=(0,8)); self.search.bind('<KeyRelease>',lambda _: self.draw_tiles())
        ctk.CTkButton(toolbar,text='Выбрать все',width=115,fg_color=ALT,command=lambda:self.select_all(True)).pack(side='left',padx=4)
        ctk.CTkButton(toolbar,text='Снять выбор',width=115,fg_color=ALT,command=lambda:self.select_all(False)).pack(side='left',padx=4)
        self.preview_btn=ctk.CTkButton(self.body,text='Загрузить следующие 12 миниатюр',fg_color=ALT,command=self.load_usb_previews); self.preview_btn.pack(anchor='w',pady=(0,8))
        self.preview=ctk.CTkScrollableFrame(self.body,fg_color=PANEL,corner_radius=13); self.preview.pack(fill='both',expand=True)
        self.hint=ctk.CTkLabel(self.preview,text='Выбери папку или подключи iPhone и нажми «Обновить».',text_color=MUTED,justify='center'); self.hint.pack(pady=100)
        self.footer=ctk.CTkFrame(self.body,fg_color=PANEL,corner_radius=12); self.footer.pack(fill='x',pady=(14,0))
        row=ctk.CTkFrame(self.footer,fg_color='transparent'); row.pack(fill='x',padx=18,pady=(13,4))
        self.status=ctk.CTkLabel(row,text='Готово к импорту',anchor='w'); self.status.pack(side='left',fill='x',expand=True)
        self.percentage=ctk.CTkLabel(row,text='0%',text_color=MUTED); self.percentage.pack(side='right')
        self.progress=ctk.CTkProgressBar(self.footer,height=12,progress_color=ACC); self.progress.set(0); self.progress.pack(fill='x',padx=18,pady=8)
        self.details=ctk.CTkLabel(self.footer,text='Файл: —    •    Скорость: —    •    Осталось: —',text_color=MUTED,anchor='w'); self.details.pack(fill='x',padx=18,pady=(1,11))
        actions=ctk.CTkFrame(self.footer,fg_color='transparent'); actions.pack(fill='x',padx=18,pady=(0,13))
        self.cancel_btn=ctk.CTkButton(actions,text='Отменить',width=120,fg_color=ALT,command=self.cancel,state='disabled'); self.cancel_btn.pack(side='right',padx=(8,0))
        self.go=ctk.CTkButton(actions,text='Настроить и экспортировать',width=240,height=40,command=self.start); self.go.pack(side='right')
        self.after(120,self.poll)
    def video_filter_changed(self, _=None):
        self.selected=set(self.visible_group_paths())
        self.draw_tiles()

    def group_changed(self, _=None):
        if self.group.get()=='Видео':
            self.video_filters.pack(side='left',padx=(12,0))
        else:
            self.video_filters.pack_forget()
        # Selection is confined to the current group: a video-only export never copies photos.
        self.selected=set(self.visible_group_paths())
        self.preview_offset=0
        self.preview_btn.configure(state='disabled' if self.group.get()=='Видео' else 'normal')
        self.draw_tiles()

    def visible_group_paths(self):
        suffixes=group_suffixes(self.group.get())
        return (x['path'] for x in self.usb_items if x['suffix'] in suffixes and (self.group.get()!='Видео' or matches_video_filter(x,self.usb_items,self.video_filter.get(),self.photo_index))) if self.usb.get() else (p for p in self.entries if p.suffix.lower() in suffixes and (self.group.get()!='Видео' or matches_video_filter({'path':str(p),'suffix':p.suffix.lower()},None,self.video_filter.get(),self.photo_index)))

    def local_media_items(self):
        return [{'path':str(p),'suffix':p.suffix.lower()} for p in self.entries]

    def source_changed(self):
        self.scan_cancel.set(); self.usb_scanning=False
        usb=self.usb.get(); self.select_source.configure(state='disabled' if usb else 'normal'); self.scan_token+=1
        self.entries=[]; self.selected=set(); self.usb_items=[]; self.photo_index=set(); self.usb_preview={}; self.source_name.configure(text='Подключённый iPhone' if usb else 'Папка не выбрана'); self.draw_tiles()
    def choose_source(self):
        path=filedialog.askdirectory(title='Выбери папку с фото и видео')
        if path:
            self.source.set(path); self.source_name.configure(text=Path(path).name); self.refresh()
    def choose_target(self):
        path=filedialog.askdirectory(title='Куда сохранить фото и видео')
        if path: self.target.set(path); self.target_name.configure(text=path if len(path)<28 else '…'+path[-26:])
    def refresh(self):
        if self.usb.get():
            self.scan_cancel.set()
            self.scan_cancel=threading.Event()
            cancelled=self.scan_cancel
            self.scan_token+=1; token=self.scan_token
            self.usb_items=[]; self.photo_index=set(); self.selected=set(); self.usb_scanning=True; self.preview_offset=0; self.usb_preview={}
            self.draw_tiles()
            self.status.configure(text='Читаем папки iPhone… первые файлы появятся по мере загрузки')
            self.percentage.configure(text='Поиск…')
            self.progress.configure(mode='indeterminate')
            self.progress.start()
            def scan_usb():
                try:
                    from iphone_usb import list_iphone_media
                    def batch(items, count):
                        if not cancelled.is_set():
                            self.events.put(('usb_batch', (token,items,count)))
                    list_iphone_media(on_batch=batch,cancelled=cancelled,batch_size=32)
                    self.events.put(('usb_scan_done',token))
                except Exception as e:self.events.put(('usb_scan_error',(token,str(e))))
            threading.Thread(target=scan_usb,daemon=True).start()
            return
        p=Path(self.source.get()) if self.source.get() else None
        if not p or not p.is_dir(): return
        self.scan_token+=1; token=self.scan_token
        self.status.configure(text='Ищем фото и видео…')
        def scan():
            try:
                paths=sorted(x for x in p.rglob('*') if x.is_file() and x.suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS))
                self.events.put(('scan',(token,paths)))
            except Exception as e:self.events.put(('error',str(e)))
        threading.Thread(target=scan,daemon=True).start()
    def select_all(self,on):
        needle=self.search.get().casefold().strip()
        visible=(p for p in self.visible_group_paths() if needle in (Path(p).name.casefold()))
        self.selected=set(visible) if on else set()
        self.draw_tiles()
    def draw_tiles(self):
        for w in self.preview.winfo_children(): w.destroy()
        if self.usb.get():
            needle=self.search.get().casefold().strip()
            group_paths=set(self.visible_group_paths())
            visible=[x for x in self.usb_items if x['path'] in group_paths and needle in x['name'].casefold()]
            self.count.configure(text=f'{len(self.selected)} выбрано / {len(visible)} в группе «{self.group.get()}»')
            if not visible:
                ctk.CTkLabel(self.preview,text='В выбранной группе файлов пока нет. Подключи iPhone и нажми «Обновить».\nФайлы iCloud могут быть недоступны.',text_color=MUTED,justify='center').pack(pady=80)
                return
            self.thumbnails=[]
            for i,x in enumerate(visible[:160]):
                r,c=divmod(i,4); key=x['path']
                tile=ctk.CTkFrame(self.preview,width=166,height=173,fg_color=ALT if key in self.selected else '#202737',corner_radius=10)
                tile.grid(row=r,column=c,padx=9,pady=9,sticky='nsew');tile.grid_propagate(False)
                local=self.usb_preview.get(key)
                if local and Path(local).is_file():
                    try:
                        with Image.open(local) as raw:
                            im=ImageOps.exif_transpose(raw);im.thumbnail((144,112)); im=im.copy()
                        thumb=ctk.CTkImage(light_image=im,dark_image=im,size=im.size)
                        self.thumbnails.append(thumb)
                        ctk.CTkLabel(tile,image=thumb,text='').pack(pady=(8,2))
                    except Exception:ctk.CTkLabel(tile,text=x['suffix'].upper(),height=114).pack(pady=(8,2))
                else:ctk.CTkLabel(tile,text=x['suffix'].upper()+(('\n'+video_category(x,photo_index=self.photo_index)) if self.group.get()=='Видео' else '\nОжидает загрузки'),height=114,text_color=MUTED).pack(pady=(8,2))
                check=ctk.CTkCheckBox(tile,text=x['name'][:22],width=150,font=('Segoe UI',10),onvalue=True,offvalue=False)
                check.pack(padx=8,pady=6)
                check.select() if key in self.selected else check.deselect()
                check.configure(command=lambda k=key,w=check:self.toggle(k,w.get()))
            for c in range(4):self.preview.grid_columnconfigure(c,weight=1)
            if len(visible)>160:ctk.CTkLabel(self.preview,text='Первые 160 файлов — уточни поиск',text_color=MUTED).grid(row=41,column=0,columnspan=4)
            return
        needle=self.search.get().casefold().strip(); group_paths=set(self.visible_group_paths())
        visible=[p for p in self.entries if p in group_paths and needle in p.name.casefold()]
        self.count.configure(text=f'{len(self.selected)} выбрано / {len(visible)} в группе «{self.group.get()}»')
        if not visible:
            ctk.CTkLabel(self.preview,text='Здесь появятся файлы выбранной группы после выбора папки',text_color=MUTED).pack(pady=95); return
        # Limit rendered thumbnails to avoid freezing the UI for huge libraries.
        shown=visible[:160]; self.thumbnails=[]
        for i,p in enumerate(shown):
            r,c=divmod(i,4)
            tile=ctk.CTkFrame(self.preview,width=166,height=172,fg_color=ALT if p in self.selected else '#202737',corner_radius=10)
            tile.grid(row=r,column=c,padx=9,pady=9,sticky='nsew'); tile.grid_propagate(False)
            try:
                with Image.open(p) as raw:
                    im=ImageOps.exif_transpose(raw); im.thumbnail((144,116)); thumb=ctk.CTkImage(light_image=im.copy(),dark_image=im.copy(),size=im.size)
                self.thumbnails.append(thumb)
                ctk.CTkLabel(tile,text='',image=thumb).pack(pady=(7,2))
            except Exception:
                ctk.CTkLabel(tile,text=p.suffix.upper(),height=116,text_color=MUTED).pack(pady=(7,2))
            check=ctk.CTkCheckBox(tile,text=p.name[:20],width=150,font=('Segoe UI',10),onvalue=True,offvalue=False)
            check.pack(padx=8,pady=6)
            check.select() if p in self.selected else check.deselect()
            check.configure(command=lambda x=p,w=check:self.toggle(x,w.get()))
        for c in range(4): self.preview.grid_columnconfigure(c,weight=1)
        if len(visible)>160: ctk.CTkLabel(self.preview,text=f'Показаны первые 160 из {len(visible)}. Уточни поиск по имени.',text_color=MUTED).grid(row=41,column=0,columnspan=4,pady=20)
    def toggle(self,p,value):
        if value:self.selected.add(p)
        else:self.selected.discard(p)
        self.count.configure(text=f'{len(self.selected)} выбрано в группе «{self.group.get()}»')
    def load_usb_previews(self):
        if self.group.get()=='Видео' or not self.usb.get() or not self.usb_items or self.running or self.preview_loading:return
        needle=self.search.get().casefold().strip()
        images=[x for x in self.usb_items if x['suffix'] in {'.heic','.heif','.jpg','.jpeg','.png','.dng','.tif','.tiff'} and needle in x['name'].casefold()]
        batch=images[self.preview_offset:self.preview_offset+12]
        self.preview_offset+=12
        if not batch:return
        from preview_cache import cache_file
        cached={x['path']:str(cache_file(self.preview_cache,x['path'])) for x in batch
                if cache_file(self.preview_cache,x['path']).is_file()}
        self.usb_preview.update(cached)
        wanted={x['path'] for x in batch if x['path'] not in cached}
        if not wanted:
            self.draw_tiles()
            return
        self.preview_loading=True
        self.status.configure(text='Загружаем миниатюры: оригиналы используются только временно…')
        def work():
            mapping={}; errors=[]
            try:
                from iphone_usb import open_afc
                from preview_cache import thumbnail_from_afc
                with open_afc() as afc:
                    for source in sorted(wanted):
                        try:
                            mapping[source]=str(thumbnail_from_afc(afc,source,self.preview_cache))
                        except Exception as exc:
                            errors.append(f'{source}: {exc}')
                self.events.put(('usb_previews',(mapping,errors)))
            except Exception as exc:
                self.events.put(('usb_preview_error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def start(self):
        if self.running:return
        if self.usb.get() and self.usb_scanning:
            messagebox.showinfo('Идёт сканирование','Дождись завершения поиска файлов, чтобы все Live Photos были распознаны.');return
        if not self.target.get():messagebox.showwarning('Папка назначения','Выбери папку сохранения.');return
        if not self.selected:messagebox.showwarning('Выбор','Выбери хотя бы один файл.');return
        dest=Path(self.target.get()); source=Path(self.source.get()) if self.source.get() else None
        if not self.usb.get() and (dest.resolve()==source.resolve() or dest.resolve() in source.resolve().parents or source.resolve() in dest.resolve().parents):
            messagebox.showerror('Небезопасная папка','Исходная и целевая папки не должны пересекаться.');return
        dialog=Settings(self,video=self.group.get()=='Видео'); self.wait_window(dialog)
        if not dialog.result:return
        opts=dialog.result; chosen=set(self.selected).intersection(set(self.visible_group_paths())); usb=self.usb.get()
        self.cancel_event.clear(); self.running=True; self.go.configure(state='disabled');self.cancel_btn.configure(state='normal');self.progress.set(0)
        self.start_clock=time.monotonic();self.last_sample=None;self.speed=None;self.status.configure(text='Начинаем перенос выбранных '+('видео…' if self.group.get()=='Видео' else 'фотографий…'))
        def worker():
            try:
                dest.mkdir(parents=True,exist_ok=True)
                if usb:
                    from iphone_usb import open_afc
                    from usb_pipeline import transfer_and_convert
                    with open_afc() as afc:
                        result,stats,converted=transfer_and_convert(
                            afc,self.usb_items,chosen,dest,opts,
                            lambda b,t,f,n,total:self.events.put(('usb',(b,t,f,n,total))),
                            self.cancel_event,dialog.result_folders)
                    self.events.put(('phase',f"Скопировано: {stats['copied']} · Уже было: {stats['skipped']} · Конвертировано: {converted}"))
                else:
                    result=export_directory(source,dest,opts,lambda n,t,f:self.events.put(('progress',(n,t,f))),self.cancel_event,selected_paths=chosen,folder_mode=dialog.result_folders)
                self.events.put(('done',result))
            except Exception as e:self.events.put(('error',str(e)))
        threading.Thread(target=worker,daemon=True).start()
    def cancel(self):self.cancel_event.set();self.cancel_btn.configure(state='disabled');self.status.configure(text='Останавливаем после текущего файла…')
    def poll(self):
        draw_needed=False
        while not self.events.empty():
            kind,v=self.events.get_nowait()
            if kind=='usb_previews':
                mapping,errs=v;self.preview_loading=False;self.usb_preview.update(mapping);self.draw_tiles()
                self.status.configure(text=f'Загружено миниатюр: {len(mapping)}; ошибок: {len(errs)}')
            elif kind=='usb_preview_error':
                self.preview_loading=False;self.status.configure(text='Не удалось прочитать миниатюры: '+v)
            elif kind=='usb_batch':
                token,items,count=v
                if token==self.scan_token:
                    self.usb_items.extend(items)
                    # Cheap incremental index; classification remains O(1) per card.
                    self.photo_index.update(photo_pair_index(items))
                    # Default selection follows the chosen group during discovery.
                    self.selected.update(x['path'] for x in items if x['suffix'] in group_suffixes(self.group.get()) and (self.group.get()!='Видео' or matches_video_filter(x,None,self.video_filter.get(),self.photo_index)))
                    self.status.configure(text=f'Найдено {count} файлов, сканирование продолжается…')
                    draw_needed=True
            elif kind=='usb_scan_done':
                if v==self.scan_token:
                    self.usb_scanning=False
                    self.selected=set(self.visible_group_paths())
                    self.progress.stop();self.progress.configure(mode='determinate');self.progress.set(0)
                    self.percentage.configure(text='Готово')
                    self.status.configure(text=f'Найдено {len(self.usb_items)} файлов. Загружаем первые миниатюры…')
                    self.after(150,self.load_usb_previews)
                    draw_needed=True
            elif kind=='usb_scan_error':
                token,msg=v
                if token==self.scan_token:
                    self.usb_scanning=False
                    self.progress.stop();self.progress.configure(mode='determinate');self.progress.set(0)
                    self.percentage.configure(text='Ошибка')
                    messagebox.showerror('iPhone',msg)
            elif kind=='scan':
                token,paths=v
                if token==self.scan_token:self.entries=paths;self.photo_index=photo_pair_index(self.local_media_items());self.selected=set(self.visible_group_paths());self.draw_tiles();self.status.configure(text='Выбери файлы и параметры экспорта')
            elif kind=='phase':self.status.configure(text=v);self.last_sample=None;self.speed=None
            elif kind in ('usb','progress'):
                now=time.monotonic()
                if kind=='usb':bytes_done,bytes_total,name,n,total=v; unit=bytes_done; whole=bytes_total; unit_name='МБ/с'
                else:n,total,name=v;unit=n;whole=total;unit_name='фото/с'
                if self.last_sample is not None:
                    dt=now-self.last_sample[0];diff=unit-self.last_sample[1]
                    if dt>=0.55 and diff>=0:
                        instant=diff/dt;self.speed=instant if self.speed is None else .25*instant+.75*self.speed;self.last_sample=(now,unit)
                else:self.last_sample=(now,unit)
                percent=min(1,max(0,unit/whole)) if whole else (n/total if total else 0)
                rate=self.speed or 0;eta=(whole-unit)/rate if (rate>0 and whole) else None
                eta_text=f'{int(eta)//3600:02}:{int(eta)//60%60:02}:{int(eta)%60:02}' if eta is not None else 'расчёт…'
                speed_text=f'{rate/1048576:.1f} МБ/с' if kind=='usb' else f'{rate:.1f} фото/с'
                self.progress.set(percent);self.percentage.configure(text=f'{percent:.0%}')
                self.status.configure(text=f'{n} из {total} файлов · '+('Копирование iPhone' if kind=='usb' else 'Обработка фотографий'))
                self.details.configure(text=f'Файл: {Path(name).name[:37]}    •    Скорость: {speed_text}    •    Осталось: {eta_text}')
            elif kind=='done':
                n,total,errors,cancelled=v;self.running=False;self.go.configure(state='normal');self.cancel_btn.configure(state='disabled')
                self.status.configure(text=f'{"Отменено" if cancelled else "Готово"}: {n}/{total}. Ошибок: {len(errors)}')
                messagebox.showinfo('Результат',f'Обработано: {n}/{total}\nОшибок: {len(errors)}\nРезультат: {self.target.get()}')
            elif kind=='error':
                self.running=False;self.go.configure(state='normal');self.cancel_btn.configure(state='disabled');self.status.configure(text='Ошибка экспорта');messagebox.showerror('Ошибка',v)
        if draw_needed and (not self.usb_scanning or time.monotonic()-self.usb_draw_at>1.0):
            self.usb_draw_at=time.monotonic()
            self.draw_tiles()
        self.after(120,self.poll)

if __name__=='__main__':App().mainloop()
