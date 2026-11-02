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
# Follow the Windows light/dark preference with an iOS-inspired palette.
ctk.set_appearance_mode('system')
ctk.set_default_color_theme('blue')
BG=('#F5F6F8','#111319')
PANEL=('#FFFFFF','#1B1D24')
ALT=('#ECF0F5','#2A2E39')
FG=('#1E2530','#F6F7FB')
MUTED=('#687586','#A4ADBD')
ACC=('#007AFF','#0A84FF')
TILE=('#FAFBFD','#232833')
SELECTED=('#E8F2FF','#203A56')

class Settings(ctk.CTkToplevel):
    """Compact, safe export sheet: optional settings only after choosing files."""

    FOLDER_OPTIONS=('По годам и месяцам','Оригинальная структура','Одна папка')
    MODES=(('original','Оригиналы · без изменений'),
           ('both','Оригиналы + JPEG'),
           ('jpeg','JPEG · совместимая копия'),
           ('tiff','TIFF · максимальный размер'))

    def __init__(self,parent,video=False):
        super().__init__(parent)
        self.video=video
        self.result=None
        self.result_folders='original'
        self.mode=tk.StringVar(value='original')
        self.quality=tk.IntVar(value=97)
        self.mov=tk.BooleanVar(value=True)
        self.folders=tk.StringVar(value='Оригинальная структура' if video else 'По годам и месяцам')
        self.title('Параметры экспорта')
        self.geometry('500x335' if video else '500x585')
        self.resizable(False,False)
        self.configure(fg_color=BG)

        content=ctk.CTkFrame(self,fg_color='transparent')
        content.pack(fill='both',expand=True,padx=26,pady=23)
        ctk.CTkLabel(content,text='Экспорт видео' if video else 'Экспорт фотографий',
                     text_color=FG,font=('Segoe UI',23,'bold')).pack(anchor='w')
        ctk.CTkLabel(content,
                     text='Файлы копируются без перекодирования.' if video
                     else 'Оригиналы сохраняют исходное качество, HDR и метаданные.',
                     text_color=MUTED,font=('Segoe UI',12)).pack(anchor='w',pady=(5,18))
        if not video:
            ctk.CTkLabel(content,text='Формат',text_color=FG,
                         font=('Segoe UI',13,'bold')).pack(anchor='w',pady=(0,7))
            options=ctk.CTkFrame(content,fg_color=PANEL,corner_radius=12)
            options.pack(fill='x')
            for mode,label in self.MODES:
                ctk.CTkRadioButton(options,text=label,variable=self.mode,value=mode,
                                   radiobutton_width=19,radiobutton_height=19,
                                   text_color=FG,font=('Segoe UI',12),
                                   command=self.update_quality).pack(anchor='w',padx=17,pady=8)

            self.quality_row=ctk.CTkFrame(content,fg_color='transparent')
            self.quality_row.pack(fill='x',pady=(12,0))
            self.qLabel=ctk.CTkLabel(self.quality_row,text='Качество JPEG: 97',
                                     text_color=MUTED,font=('Segoe UI',12))
            self.qLabel.pack(anchor='w')
            self.slider=ctk.CTkSlider(self.quality_row,from_=85,to=100,
                                       number_of_steps=15,command=self.change_q)
            self.slider.set(97)
            self.slider.pack(fill='x',pady=(4,0))
            self.live=ctk.CTkCheckBox(content,text='Сохранить движение Live Photos (MOV)',
                                      variable=self.mov,text_color=FG,
                                      font=('Segoe UI',12))
            self.live.pack(anchor='w',pady=(16,10))
            self.update_quality()

        ctk.CTkLabel(content,text='Организация файлов',font=('Segoe UI',13,'bold'),
                     text_color=FG).pack(anchor='w',pady=(12,7))
        self.folder_control=ctk.CTkOptionMenu(
            content,values=list(self.FOLDER_OPTIONS),variable=self.folders,
            height=38,corner_radius=9,fg_color=ALT,
            button_color=ALT,button_hover_color=SELECTED,text_color=FG)
        self.folder_control.pack(fill='x')
        if not video:
            ctk.CTkLabel(content,text='При USB-экспорте оригинал сохраняется даже при выборе JPEG.',
                         text_color=MUTED,font=('Segoe UI',11)).pack(anchor='w',pady=(9,0))
        controls=ctk.CTkFrame(content,fg_color='transparent')
        controls.pack(side='bottom',fill='x',pady=(17,0))
        ctk.CTkButton(controls,text='Начать экспорт',width=175,height=42,
                      corner_radius=11,fg_color=ACC,
                      command=self.confirm).pack(side='right')
        ctk.CTkButton(controls,text='Отмена',width=88,height=42,
                      corner_radius=11,fg_color=ALT,hover_color=SELECTED,
                      text_color=FG,command=self.destroy).pack(side='right',padx=(0,8))
        self.transient(parent)
        self.grab_set()
        self.focus_set()

    def update_quality(self):
        if self.video:return
        if self.mode.get() in ('jpeg','both'):
            if not self.quality_row.winfo_manager():
                self.quality_row.pack(fill='x',pady=(12,0),before=self.live)
        else:
            self.quality_row.pack_forget()

    def change_q(self,value):
        self.quality.set(int(round(value)))
        self.qLabel.configure(text=f'Качество JPEG: {self.quality.get()}')

    def confirm(self):
        folders=self.folders.get()
        self.result_folders=('year-month' if folders=='По годам и месяцам'
                             else 'flat' if folders=='Одна папка'
                             else 'original')
        self.result=ExportOptions('original',97,False) if self.video else ExportOptions(
            self.mode.get(),self.quality.get(),self.mov.get())
        self.destroy()


class App(ctk.CTk):
    """One clear import flow, with Windows-native layout and iOS-like visual restraint."""

    def __init__(self):
        super().__init__()
        self.title('Hush Photo')
        self.geometry('1160x760')
        self.minsize(1020,640)
        self.configure(fg_color=BG)

        self.source=tk.StringVar()
        self.target=tk.StringVar()
        self.usb=tk.BooleanVar(value=True)
        self.source_mode=tk.StringVar(value='iPhone')
        self.active_usb=True
        self.group=tk.StringVar(value='Фото')
        self.video_filter=tk.StringVar(value='Все видео')
        self.displayed_group='Фото'
        self.selected_by_group={'Фото':None,'Видео':None}
        self.page=0
        self.page_size=36
        self.photo_index=set()
        self.entries=[]
        self.selected=set()
        self.usb_items=[]
        self.usb_preview={}
        self.preview_cache=Path(__import__('os').environ.get(
            'LOCALAPPDATA',str(Path.home()/'AppData'/'Local'))) / 'HushPhoto' / 'previews'
        self.thumbnails=[]
        self.events=queue.Queue()
        self.cancel_event=threading.Event()
        self.running=False
        from preview_cache import clear_legacy_cache,trim_cache
        clear_legacy_cache(self.preview_cache)
        trim_cache(self.preview_cache)
        self.last_sample=None
        self.speed=None
        self.scan_token=0
        self.start_clock=0
        self.scan_cancel=threading.Event()
        self.usb_scanning=False
        self.local_scanning=False
        self.usb_draw_at=0
        self.preview_offset=0
        self.preview_loading=False
        self.tile_checks=[]
        self.export_result=False
        self.scan_error=None
        self.scanned=False

        self.header=ctk.CTkFrame(self,fg_color=PANEL,corner_radius=0,height=76)
        self.header.pack(fill='x')
        self.header.pack_propagate(False)
        logo=ctk.CTkFrame(self.header,fg_color='transparent')
        logo.pack(side='left',padx=30,pady=17)
        ctk.CTkLabel(logo,text='◉',text_color=ACC,font=('Segoe UI',27)).pack(side='left',padx=(0,12))
        brand=ctk.CTkFrame(logo,fg_color='transparent')
        brand.pack(side='left')
        ctk.CTkLabel(brand,text='Hush Photo',text_color=FG,
                     font=('Segoe UI',21,'bold')).pack(anchor='w')
        ctk.CTkLabel(brand,text='Фото и видео — без облака и сжатия',
                     text_color=MUTED,font=('Segoe UI',11)).pack(anchor='w')
        ctk.CTkLabel(self.header,text='Локальный перенос  ·  Windows',
                     text_color=MUTED,font=('Segoe UI',12)).pack(side='right',padx=30)

        self.shell=ctk.CTkFrame(self,fg_color='transparent')
        self.shell.pack(fill='both',expand=True,padx=22,pady=20)

        self.sidebar=ctk.CTkFrame(self.shell,width=272,fg_color=PANEL,corner_radius=18)
        self.sidebar.pack(side='left',fill='y',padx=(0,18))
        self.sidebar.pack_propagate(False)
        ctk.CTkLabel(self.sidebar,text='Устройство',font=('Segoe UI',18,'bold'),
                     text_color=FG).pack(anchor='w',padx=20,pady=(25,4))
        ctk.CTkLabel(self.sidebar,text='Выберите источник файлов',
                     text_color=MUTED,font=('Segoe UI',12)).pack(anchor='w',padx=20)

        self.source_switch=ctk.CTkSegmentedButton(
            self.sidebar,values=['iPhone','Папка'],variable=self.source_mode,
            command=self.source_mode_changed,height=36,corner_radius=9,
            fg_color=ALT,selected_color=ACC,selected_hover_color=ACC,
            unselected_color=ALT,unselected_hover_color=SELECTED,
            text_color=FG)
        self.source_switch.pack(fill='x',padx=18,pady=(22,15))

        device=ctk.CTkFrame(self.sidebar,fg_color=ALT,corner_radius=12)
        device.pack(fill='x',padx=18)
        self.connection_badge=ctk.CTkLabel(
            device,text='●  Ожидает подключения',font=('Segoe UI',12),
            text_color=MUTED,anchor='w')
        self.connection_badge.pack(fill='x',padx=14,pady=(13,4))
        self.device_card=device
        self.source_name=ctk.CTkLabel(
            device,text='Подключите разблокированный iPhone',
            text_color=FG,font=('Segoe UI',12),
            justify='left',anchor='w',wraplength=207)
        self.source_name.pack(fill='x',padx=14,pady=(0,13))
        self.select_source=ctk.CTkButton(
            self.sidebar,text='Выбрать папку',height=36,
            fg_color=ALT,text_color=FG,hover_color=SELECTED,
            corner_radius=9,command=self.choose_source)
        # Local source chooser only appears in folder mode.

        ctk.CTkFrame(self.sidebar,height=1,fg_color=ALT).pack(fill='x',padx=20,pady=25)
        ctk.CTkLabel(self.sidebar,text='Сохранить в',font=('Segoe UI',18,'bold'),
                     text_color=FG).pack(anchor='w',padx=20,pady=(0,12))
        self.target_btn=ctk.CTkButton(
            self.sidebar,text='Выбрать папку назначения   →',height=42,
            corner_radius=11,fg_color=ALT,hover_color=SELECTED,
            text_color=FG,command=self.choose_target)
        self.target_btn.pack(fill='x',padx=18)
        self.target_name=ctk.CTkLabel(
            self.sidebar,text='Папка ещё не выбрана',font=('Segoe UI',11),
            text_color=MUTED,justify='left',anchor='w',wraplength=222)
        self.target_name.pack(fill='x',padx=21,pady=(10,0))

        self.sidebar_hint=ctk.CTkLabel(
            self.sidebar,text='Для доступа к iPhone разблокируйте\n'
                              'его и нажмите «Доверять».\n'
                              'Оригиналы остаются на устройстве.',
            text_color=MUTED,font=('Segoe UI',11),
            justify='left',anchor='w')
        self.sidebar_hint.pack(side='bottom',anchor='w',padx=21,pady=24)

        self.body=ctk.CTkFrame(self.shell,fg_color='transparent')
        self.body.pack(side='left',fill='both',expand=True)

        heading=ctk.CTkFrame(self.body,fg_color='transparent')
        heading.pack(fill='x',pady=(2,16))
        caption=ctk.CTkFrame(heading,fg_color='transparent')
        caption.pack(side='left')
        ctk.CTkLabel(caption,text='Медиатека',text_color=FG,
                     font=('Segoe UI',27,'bold')).pack(anchor='w')
        self.count=ctk.CTkLabel(caption,text='Пока нет файлов',
                                text_color=MUTED,font=('Segoe UI',12))
        self.count.pack(anchor='w',pady=(2,0))
        self.refresh_btn=ctk.CTkButton(
            heading,text='↻  Обновить',width=116,height=36,
            fg_color=ALT,hover_color=SELECTED,text_color=FG,
            corner_radius=10,command=self.refresh)
        # Refresh appears with a loaded media library, not on the welcome screen.

        self.tools=ctk.CTkFrame(self.body,fg_color='transparent')
        groups=ctk.CTkFrame(self.tools,fg_color='transparent')
        groups.pack(fill='x',pady=(0,12))
        self.group_tabs=ctk.CTkSegmentedButton(
            groups,values=['Фото','Видео'],variable=self.group,
            command=self.group_changed,height=36,
            selected_color=ACC,corner_radius=10)
        self.group_tabs.pack(side='left')
        self.video_filters=ctk.CTkSegmentedButton(
            groups,values=['Все видео','Видеоролики','Live Photos'],
            variable=self.video_filter,command=self.video_filter_changed,
            height=36,corner_radius=10)
        toolbar=ctk.CTkFrame(self.tools,fg_color='transparent')
        toolbar.pack(fill='x',pady=(0,13))
        self.search=ctk.CTkEntry(
            toolbar,placeholder_text='Поиск по имени файла',height=38,
            corner_radius=10,fg_color=PANEL,border_color=ALT)
        self.search.pack(side='left',fill='x',expand=True,padx=(0,9))
        self.search.bind('<KeyRelease>',lambda _:self.reset_page())
        self.all_btn=ctk.CTkButton(
            toolbar,text='Выбрать всё',width=106,height=38,
            fg_color=ALT,hover_color=SELECTED,text_color=FG,
            corner_radius=10,command=lambda:self.select_all(True))
        self.all_btn.pack(side='left',padx=(0,7))
        self.none_btn=ctk.CTkButton(
            toolbar,text='Снять выбор',width=108,height=38,
            fg_color=ALT,hover_color=SELECTED,text_color=FG,
            corner_radius=10,command=lambda:self.select_all(False))
        self.none_btn.pack(side='left')
        self.preview_btn=ctk.CTkButton(
            self.tools,text='Загрузить ещё 12 миниатюр',height=32,
            fg_color='transparent',hover_color=ALT,text_color=ACC,
            anchor='w',command=self.load_usb_previews)

        self.empty=ctk.CTkFrame(self.body,fg_color=PANEL,corner_radius=18)
        self.empty.pack(fill='both',expand=True)
        self.empty_center=ctk.CTkFrame(self.empty,fg_color='transparent')
        self.empty_center.place(relx=.5,rely=.47,anchor='center')
        ctk.CTkLabel(self.empty_center,text='▧',font=('Segoe UI',57),
                     text_color=ACC).pack(pady=(0,12))
        self.empty_title=ctk.CTkLabel(
            self.empty_center,text='Ваши фотографии — здесь',
            text_color=FG,font=('Segoe UI',21,'bold'))
        self.empty_title.pack(pady=(0,9))
        self.empty_desc=ctk.CTkLabel(
            self.empty_center,text='Подключите iPhone по USB, разблокируйте его\n'
                                   'и найдите свои фото и видео.',
            text_color=MUTED,justify='center',wraplength=425,
            font=('Segoe UI',13))
        self.empty_desc.pack(pady=(0,24))
        self.empty_action=ctk.CTkButton(
            self.empty_center,text='Найти фото и видео',height=44,width=205,
            fg_color=ACC,corner_radius=11,
            font=('Segoe UI',13,'bold'),command=self.empty_primary_action)
        self.empty_action.pack()
        self.preview=ctk.CTkScrollableFrame(
            self.body,fg_color=PANEL,corner_radius=16)
        pager=ctk.CTkFrame(self.body,fg_color='transparent')
        self.pager=pager
        self.page_back=ctk.CTkButton(
            pager,text='← Назад',width=100,height=32,
            fg_color=ALT,hover_color=SELECTED,text_color=FG,
            command=lambda:self.change_page(-1))
        self.page_back.pack(side='left')
        self.page_info=ctk.CTkLabel(pager,text='',text_color=MUTED)
        self.page_info.pack(side='left',padx=14)
        self.page_forward=ctk.CTkButton(
            pager,text='Далее →',width=100,height=32,
            fg_color=ALT,hover_color=SELECTED,text_color=FG,
            command=lambda:self.change_page(1))
        self.page_forward.pack(side='right')

        self.footer=ctk.CTkFrame(self.body,fg_color=PANEL,corner_radius=15)
        self.footer.pack(fill='x',pady=(13,0))
        footer_row=ctk.CTkFrame(self.footer,fg_color='transparent')
        footer_row.pack(fill='x',padx=18,pady=14)
        summary=ctk.CTkFrame(footer_row,fg_color='transparent')
        summary.pack(side='left',fill='x',expand=True)
        self.status=ctk.CTkLabel(
            summary,text='Готово к подключению',font=('Segoe UI',13,'bold'),
            text_color=FG,anchor='w')
        self.status.pack(anchor='w')
        self.details=ctk.CTkLabel(
            summary,text='Выберите файлы для экспорта',
            font=('Segoe UI',11),text_color=MUTED,anchor='w')
        self.details.pack(anchor='w')
        self.cancel_btn=ctk.CTkButton(
            footer_row,text='Отменить',width=98,height=42,
            fg_color=ALT,hover_color=SELECTED,text_color=FG,
            corner_radius=11,command=self.cancel)
        self.go=ctk.CTkButton(
            footer_row,text='Экспортировать',width=180,height=42,
            fg_color=ACC,corner_radius=11,
            font=('Segoe UI',13,'bold'),command=self.start,state='disabled')
        self.go.pack(side='right')
        progress_row=ctk.CTkFrame(self.footer,fg_color='transparent')
        self.progress_row=progress_row
        self.progress=ctk.CTkProgressBar(
            progress_row,height=6,corner_radius=8,progress_color=ACC)
        self.progress.set(0)
        self.progress.pack(side='left',fill='x',expand=True,padx=(0,12))
        self.percentage=ctk.CTkLabel(
            progress_row,text='0%',width=50,
            font=('Segoe UI',11),text_color=MUTED)
        self.percentage.pack(side='right')

        self._update_empty_state()
        self.after(120,self.poll)

    def source_mode_changed(self, mode):
        self.usb.set(mode=='iPhone')
        self.source_changed()

    def stop_scan(self):
        if self.usb_scanning or self.local_scanning:
            self.scan_cancel.set()
            self.status.configure(text='Останавливаем поиск…')
            self.empty_action.configure(state='disabled')
            self.refresh_btn.configure(state='disabled')

    def empty_primary_action(self):
        if self.usb_scanning or self.local_scanning:
            self.stop_scan()
            return
        if self.usb.get():
            self.refresh()
        elif self.scanned or not self.source.get():
            self.choose_source()
        else:
            self.refresh()

    def _update_empty_state(self):
        """Show actions only when they can be used; never show an empty scroll bar."""
        if self.scan_error:
            title='Не удалось открыть медиатеку'
            desc=self.scan_error[:180]
            button='Повторить поиск' if self.usb.get() or self.source.get() else 'Выбрать папку'
        elif self.usb_scanning or self.local_scanning:
            title='Ищем фотографии…'
            desc='Считываем доступные файлы с устройства.\nЭто может занять немного времени.'
            button='Остановить поиск'
        elif self.scanned and not (self.usb_items if self.usb.get() else self.entries):
            title='Файлы не найдены'
            desc=('На iPhone нет доступных фото и видео в DCIM.\n'
                  'Проверьте загрузку оригиналов из iCloud.' if self.usb.get()
                  else 'В папке нет поддерживаемых изображений или видео.\n'
                       'Можно выбрать другую папку.')
            button='Повторить поиск' if self.usb.get() else 'Выбрать другую папку'
        elif self.usb.get():
            title='Фотографии с вашего iPhone'
            desc='Подключите и разблокируйте iPhone.\nПодтвердите «Доверять» и начните поиск.'
            button='Найти фото и видео'
        else:
            title='Добавьте фотографии'
            desc='Выберите папку на компьютере,\nчтобы увидеть фотографии и видео.'
            button='Выбрать папку' if not self.source.get() else 'Показать файлы'
        self.empty_title.configure(text=title)
        self.empty_desc.configure(text=desc)
        self.empty_action.configure(text=button,state='normal')

    def _display_library(self, shown):
        """Swap an illustrated empty state for the actual library; no blank controls."""
        if shown:
            self.refresh_btn.configure(text='Остановить поиск' if self.usb_scanning or self.local_scanning else '↻  Обновить',
                                       command=self.stop_scan if self.usb_scanning or self.local_scanning else self.refresh,
                                       state='disabled' if self.scan_cancel.is_set() and (self.usb_scanning or self.local_scanning) else 'normal')
            if not self.refresh_btn.winfo_manager():
                self.refresh_btn.pack(side='right',pady=8)
            self.empty.pack_forget()
            if not self.tools.winfo_manager():
                self.tools.pack(fill='x',before=self.footer)
            if not self.preview._parent_frame.winfo_manager():
                self.preview.pack(fill='both',expand=True,before=self.footer)
            if not self.pager.winfo_manager():
                self.pager.pack(fill='x',pady=(9,0),before=self.footer)
            if self.usb.get() and self.group.get()=='Фото':
                if not self.preview_btn.winfo_manager():
                    self.preview_btn.pack(anchor='w')
            else:
                self.preview_btn.pack_forget()
        else:
            self.refresh_btn.pack_forget()
            self.tools.pack_forget()
            self.preview_btn.pack_forget()
            self.preview.pack_forget()
            self.pager.pack_forget()
            if not self.empty.winfo_manager():
                self.empty.pack(fill='both',expand=True,before=self.footer)
            self._update_empty_state()

    def _update_selection(self):
        count=len(self.selected)
        available=len(self.usb_items) if self.usb.get() else len(self.entries)
        if available:
            self.count.configure(text=f'{count} выбрано  ·  {available} файлов найдено')
        else:
            self.count.configure(text='Пока нет файлов')
        if not self.running:
            self.go.configure(state='normal' if count and self.scanned and not self.usb_scanning and not self.local_scanning else 'disabled',
                              text=f'Экспортировать · {count}' if count else 'Экспортировать')
            if not self.export_result:
                self.details.configure(text='Выберите файлы и папку для экспорта' if count else 'Выберите файлы для экспорта')

    def reset_page(self):
        self.page=0
        self.draw_tiles()

    def change_page(self, step):
        self.page=max(0,self.page+step)
        self.draw_tiles()

    def _page_items(self, visible):
        total=len(visible)
        pages=max(1,(total+self.page_size-1)//self.page_size)
        self.page=min(self.page,pages-1)
        self.page_info.configure(text=f'{self.page+1} / {pages} · {total} файлов' if total else '0 файлов')
        self.page_back.configure(state='normal' if self.page>0 else 'disabled')
        self.page_forward.configure(state='normal' if self.page+1<pages else 'disabled')
        first=self.page*self.page_size
        return visible[first:first+self.page_size]

    def set_running(self, running):
        self.running=running
        state='disabled' if running else 'normal'
        for control in (self.source_switch,self.select_source,self.target_btn,
                        self.refresh_btn,self.group_tabs,self.video_filters,self.search,
                        self.all_btn,self.none_btn,self.empty_action):
            control.configure(state=state)
        self.go.configure(state=state)
        for checkbox in self.tile_checks:
            checkbox.configure(state=state)
        if running:self.cancel_btn.pack(side='right',padx=(10,0),before=self.go)
        else:self.cancel_btn.pack_forget()
        self.preview_btn.configure(state='disabled' if running or not self.usb.get() or self.group.get()=='Видео' else 'normal')
        if not running:self._update_selection()

    def video_filter_changed(self, _=None):
        self.reset_page()

    def group_changed(self, _=None):
        if self.running:
            self.group.set(self.displayed_group)
            return
        self.selected_by_group[self.displayed_group]=set(self.selected)
        self.displayed_group=self.group.get()
        if self.group.get()=='Видео':
            self.video_filters.pack(side='left',padx=(12,0))
        else:
            self.video_filters.pack_forget()
        # Remember choices independently for photos and videos, including no selection.
        remembered=self.selected_by_group[self.displayed_group]
        self.selected=set(self.visible_group_paths()) if remembered is None else set(remembered)
        self.page=0
        self.preview_offset=0
        self.preview_btn.configure(state='disabled' if self.group.get()=='Видео' or not self.usb.get() else 'normal')
        self.draw_tiles()

    def visible_group_paths(self):
        suffixes=group_suffixes(self.group.get())
        return (x['path'] for x in self.usb_items if x['suffix'] in suffixes and (self.group.get()!='Видео' or matches_video_filter(x,self.usb_items,self.video_filter.get(),self.photo_index))) if self.usb.get() else (p for p in self.entries if p.suffix.lower() in suffixes and (self.group.get()!='Видео' or matches_video_filter({'path':str(p),'suffix':p.suffix.lower()},None,self.video_filter.get(),self.photo_index)))

    def local_media_items(self):
        return [{'path':str(p),'suffix':p.suffix.lower()} for p in self.entries]

    def source_changed(self):
        if self.running:
            self.usb.set(self.active_usb)
            self.source_mode.set('iPhone' if self.active_usb else 'Папка')
            return
        self.active_usb=self.usb.get()
        self.scan_error=None
        self.scanned=False
        self.scan_cancel.set(); self.usb_scanning=False
        self.preview_loading=False
        self.progress.stop();self.progress_row.pack_forget()
        usb=self.usb.get(); self.scan_token+=1
        if usb:
            self.select_source.pack_forget()
        elif not self.select_source.winfo_manager():
            self.select_source.pack(fill='x',padx=18,pady=(12,0),after=self.device_card)
        self.connection_badge.configure(text='●  Ожидает подключения' if usb else '●  Локальная папка',text_color=MUTED)
        self.entries=[]; self.selected=set(); self.selected_by_group={'Фото':None,'Видео':None}; self.page=0; self.usb_items=[]; self.photo_index=set(); self.usb_preview={}; self.local_scanning=False; self.preview_btn.configure(state='normal' if usb and self.group.get()=='Фото' else 'disabled'); self.source_name.configure(text='Подключите разблокированный iPhone' if usb else (Path(self.source.get()).name if self.source.get() else 'Папка не выбрана')); self.export_result=False; self.draw_tiles(); self.status.configure(text='Готово к подключению')
    def choose_source(self):
        if self.running:return
        path=filedialog.askdirectory(title='Выбери папку с фото и видео')
        if path:
            self.source.set(path); self.source_name.configure(text=Path(path).name); self.connection_badge.configure(text='●  Папка выбрана',text_color=ACC); self.refresh()
    def choose_target(self):
        if self.running:return
        path=filedialog.askdirectory(title='Куда сохранить фото и видео')
        if path: self.target.set(path); self.target_name.configure(text=path if len(path)<28 else '…'+path[-26:])
    def refresh(self):
        if self.running:return
        self.scan_error=None
        self.scanned=False
        self.preview_loading=False
        self.page=0
        self.selected_by_group={'Фото':None,'Видео':None}
        if self.usb.get():
            self.scan_cancel.set()
            self.scan_cancel=threading.Event()
            cancelled=self.scan_cancel
            self.scan_token+=1; token=self.scan_token
            self.usb_items=[]; self.photo_index=set(); self.selected=set(); self.usb_scanning=True; self.preview_offset=0; self.usb_preview={}
            self.draw_tiles()
            self.connection_badge.configure(text='●  Поиск на iPhone…',text_color=ACC)
            self.status.configure(text='Читаем папки iPhone…')
            self.percentage.configure(text='Поиск…')
            self.progress_row.pack(fill='x',padx=18,pady=(0,12))
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
                except InterruptedError:
                    self.events.put(('usb_scan_cancelled',token))
                except Exception as e:self.events.put(('usb_scan_error',(token,str(e))))
            threading.Thread(target=scan_usb,daemon=True).start()
            return
        p=Path(self.source.get()) if self.source.get() else None
        if not p or not p.is_dir(): return
        self.scan_cancel.set()
        self.scan_cancel=threading.Event()
        scan_cancel=self.scan_cancel
        self.local_scanning=True
        self.draw_tiles()
        self.scan_token+=1; token=self.scan_token
        self.status.configure(text='Ищем фото и видео…')
        def scan():
            try:
                paths=[]
                for item in p.rglob('*'):
                    if scan_cancel.is_set():
                        self.events.put(('local_scan_cancelled',token));return
                    if item.is_file() and item.suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS):
                        paths.append(item)
                self.events.put(('scan',(token,sorted(paths))))
            except Exception as e:self.events.put(('local_scan_error',(token,str(e))))
        threading.Thread(target=scan,daemon=True).start()
    def select_all(self,on):
        if self.running or self.usb_scanning or self.local_scanning:return
        needle=self.search.get().casefold().strip()
        visible={p for p in self.visible_group_paths() if needle in Path(p).name.casefold()}
        # Searching the view should not silently discard hidden selections.
        if on:self.selected.update(visible)
        else:self.selected.difference_update(visible)
        self.draw_tiles()
    def draw_tiles(self):
        self.tile_checks=[]
        for w in self.preview.winfo_children(): w.destroy()
        has_any=bool(self.usb_items if self.usb.get() else self.entries) and (self.scanned or self.usb_scanning or self.local_scanning)
        self._display_library(has_any)
        self._update_selection()
        if not has_any:return
        if self.usb.get():
            needle=self.search.get().casefold().strip()
            group_paths=set(self.visible_group_paths())
            visible=[x for x in self.usb_items if x['path'] in group_paths and needle in x['name'].casefold()]
            self.count.configure(text=f'{len(self.selected)} выбрано / {len(visible)} в группе «{self.group.get()}»')
            page_items=self._page_items(visible)
            if not visible:
                ctk.CTkLabel(self.preview,text='В этой категории нет файлов.\nПопробуйте переключить Фото / Видео или изменить поиск.',text_color=MUTED,justify='center').pack(pady=80)
                return
            self.thumbnails=[]
            for i,x in enumerate(page_items):
                r,c=divmod(i,4); key=x['path']
                tile=ctk.CTkFrame(self.preview,width=156,height=170,fg_color=SELECTED if key in self.selected else TILE,corner_radius=12,border_width=1,border_color=ACC if key in self.selected else ALT)
                tile.grid(row=r,column=c,padx=7,pady=7,sticky='nsew');tile.grid_propagate(False)
                local=self.usb_preview.get(key)
                if local and Path(local).is_file():
                    try:
                        with Image.open(local) as raw:
                            im=ImageOps.exif_transpose(raw);im.thumbnail((132,108)); im=im.copy()
                        thumb=ctk.CTkImage(light_image=im,dark_image=im,size=im.size)
                        self.thumbnails.append(thumb)
                        ctk.CTkLabel(tile,image=thumb,text='').pack(pady=(8,2))
                    except Exception:ctk.CTkLabel(tile,text=x['suffix'].upper(),height=114).pack(pady=(8,2))
                else:ctk.CTkLabel(tile,text=('▧\n'+x['suffix'].lstrip('.').upper()) if self.group.get()=='Фото' else ('▷\n'+video_category(x,photo_index=self.photo_index)),height=114,text_color=MUTED).pack(pady=(8,2))
                check=ctk.CTkCheckBox(tile,text=x['name'][:22],width=140,font=('Segoe UI',10),onvalue=True,offvalue=False,checkbox_width=20,checkbox_height=20,corner_radius=6)
                check.pack(padx=8,pady=6)
                self.tile_checks.append(check)
                check.select() if key in self.selected else check.deselect()
                check.configure(command=lambda k=key,w=check:self.toggle(k,w.get()))
            for c in range(4):self.preview.grid_columnconfigure(c,weight=1)
            return
        needle=self.search.get().casefold().strip(); group_paths=set(self.visible_group_paths())
        visible=[p for p in self.entries if p in group_paths and needle in p.name.casefold()]
        self.count.configure(text=f'{len(self.selected)} выбрано / {len(visible)} в группе «{self.group.get()}»')
        shown=self._page_items(visible)
        if not visible:
            ctk.CTkLabel(self.preview,text='В этой категории нет файлов.\nПопробуйте изменить фильтр или поиск.',text_color=MUTED).pack(pady=95); return
        # Keep large libraries responsive with bounded thumbnail pages.
        self.thumbnails=[]
        for i,p in enumerate(shown):
            r,c=divmod(i,4)
            tile=ctk.CTkFrame(self.preview,width=156,height=170,fg_color=SELECTED if p in self.selected else TILE,corner_radius=12,border_width=1,border_color=ACC if p in self.selected else ALT)
            tile.grid(row=r,column=c,padx=7,pady=7,sticky='nsew'); tile.grid_propagate(False)
            try:
                with Image.open(p) as raw:
                    im=ImageOps.exif_transpose(raw); im.thumbnail((132,108)); thumb=ctk.CTkImage(light_image=im.copy(),dark_image=im.copy(),size=im.size)
                self.thumbnails.append(thumb)
                ctk.CTkLabel(tile,text='',image=thumb).pack(pady=(7,2))
            except Exception:
                ctk.CTkLabel(tile,text=p.suffix.upper(),height=116,text_color=MUTED).pack(pady=(7,2))
            check=ctk.CTkCheckBox(tile,text=p.name[:20],width=140,font=('Segoe UI',10),onvalue=True,offvalue=False,checkbox_width=20,checkbox_height=20,corner_radius=6)
            check.pack(padx=8,pady=6)
            self.tile_checks.append(check)
            check.select() if p in self.selected else check.deselect()
            check.configure(command=lambda x=p,w=check:self.toggle(x,w.get()))
        for c in range(4): self.preview.grid_columnconfigure(c,weight=1)
    def toggle(self,p,value):
        if self.running:return
        if value:self.selected.add(p)
        else:self.selected.discard(p)
        self._update_selection()
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
        token=self.scan_token
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
                self.events.put(('usb_previews',(token,mapping,errors)))
            except Exception as exc:
                self.events.put(('usb_preview_error',(token,str(exc))))
        threading.Thread(target=work,daemon=True).start()

    def start(self):
        if self.running:return
        if not self.usb.get() and (not self.source.get() or not Path(self.source.get()).is_dir()):
            messagebox.showwarning('Источник','Сначала выбери доступную папку с файлами.');return
        if self.usb.get() and self.usb_scanning:
            messagebox.showinfo('Идёт сканирование','Дождись завершения поиска файлов, чтобы все Live Photos были распознаны.');return
        if not self.target.get():
            self.choose_target()
            if not self.target.get():return
        if not self.selected:messagebox.showwarning('Выбор','Выбери хотя бы один файл.');return
        dest=Path(self.target.get()); source=Path(self.source.get()) if self.source.get() else None
        if not self.usb.get() and (dest.resolve()==source.resolve() or dest.resolve() in source.resolve().parents or source.resolve() in dest.resolve().parents):
            messagebox.showerror('Небезопасная папка','Исходная и целевая папки не должны пересекаться.');return
        dialog=Settings(self,video=self.group.get()=='Видео'); self.wait_window(dialog)
        if not dialog.result:return
        opts=dialog.result; chosen={p for p in self.selected if Path(p).suffix.lower() in group_suffixes(self.group.get())}; usb=self.usb.get()
        self.cancel_event.clear(); self.export_result=False; self.set_running(True); self.progress.configure(mode='determinate'); self.progress.set(0); self.progress_row.pack(fill='x',padx=18,pady=(0,12))
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
                token,mapping,errs=v
                if token!=self.scan_token:continue
                self.preview_loading=False;self.usb_preview.update(mapping);self.draw_tiles()
                self.status.configure(text=f'Загружено миниатюр: {len(mapping)}; ошибок: {len(errs)}')
            elif kind=='usb_preview_error':
                token,msg=v
                if token!=self.scan_token:continue
                self.preview_loading=False;self.status.configure(text='Не удалось прочитать миниатюры: '+msg)
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
                    self.refresh_btn.configure(state='normal')
                    self.scanned=True
                    self.connection_badge.configure(text='●  iPhone обнаружен',text_color=ACC)
                    self.selected=set(self.visible_group_paths()); self.selected_by_group={'Фото':None,'Видео':None}
                    self.progress.stop();self.progress.configure(mode='determinate');self.progress.set(0);self.progress_row.pack_forget()
                    self.percentage.configure(text='Готово')
                    self.status.configure(text=f'Найдено {len(self.usb_items)} файлов' if not self.usb_items else f'Найдено {len(self.usb_items)} файлов · загрузка миниатюр')
                    if self.usb_items:self.after(150,self.load_usb_previews)
                    draw_needed=True
            elif kind=='usb_scan_cancelled':
                if v==self.scan_token:
                    self.usb_scanning=False
                    self.refresh_btn.configure(state='normal')
                    self.progress.stop();self.progress.configure(mode='determinate')
                    self.progress_row.pack_forget()
                    self.scanned=False
                    self.status.configure(text='Поиск остановлен')
                    self.draw_tiles()
            elif kind=='local_scan_cancelled':
                if v==self.scan_token:
                    self.local_scanning=False
                    self.refresh_btn.configure(state='normal')
                    self.status.configure(text='Поиск остановлен')
                    self.draw_tiles()
            elif kind=='usb_scan_error':
                token,msg=v
                if token==self.scan_token:
                    self.usb_scanning=False
                    self.refresh_btn.configure(state='normal')
                    self.scan_error=msg
                    self.connection_badge.configure(text='●  Нет соединения',text_color=MUTED)
                    self.draw_tiles()
                    self.progress.stop();self.progress.configure(mode='determinate');self.progress.set(0);self.progress_row.pack_forget()
                    self.percentage.configure(text='Ошибка')
                    self.status.configure(text='Проверьте подключение iPhone')
            elif kind=='local_scan_error':
                token,msg=v
                if token==self.scan_token:
                    self.local_scanning=False;self.scan_error=msg;self.draw_tiles();self.status.configure(text='Не удалось прочитать папку')
            elif kind=='scan':
                token,paths=v
                if token==self.scan_token:self.local_scanning=False;self.refresh_btn.configure(state='normal');self.scanned=True;self.scan_error=None;self.entries=paths;self.photo_index=photo_pair_index(self.local_media_items());self.selected=set(self.visible_group_paths());self.selected_by_group={'Фото':None,'Видео':None};self.draw_tiles();self.status.configure(text='Выберите файлы для экспорта')
            elif kind=='phase':self.status.configure(text=v);self.last_sample=None;self.speed=None
            elif kind in ('usb','progress'):
                now=time.monotonic()
                if kind=='usb':bytes_done,bytes_total,name,n,total=v; unit=bytes_done; whole=bytes_total
                else:n,total,name=v;unit=n;whole=total
                if self.last_sample is not None:
                    dt=now-self.last_sample[0];diff=unit-self.last_sample[1]
                    if dt>=0.55 and diff>=0:
                        instant=diff/dt;self.speed=instant if self.speed is None else .25*instant+.75*self.speed;self.last_sample=(now,unit)
                else:self.last_sample=(now,unit)
                percent=min(1,max(0,unit/whole)) if whole else (n/total if total else 0)
                rate=self.speed or 0
                # AFC may not know the total byte count: estimate ETA from completed files.
                if whole and rate>0:eta=(whole-unit)/rate
                elif n>0 and total>n:eta=(total-n)*max(0.01,now-self.start_clock)/n
                else:eta=None
                eta_text=f'{int(eta)//3600:02}:{int(eta)//60%60:02}:{int(eta)%60:02}' if eta is not None else 'расчёт…'
                speed_text=f'{rate/1048576:.1f} МБ/с' if kind=='usb' else f'{rate:.1f} файл/с'
                self.progress.set(percent);self.percentage.configure(text=f'{percent:.0%}')
                self.status.configure(text=f'{n} из {total} файлов · '+('Копирование iPhone' if kind=='usb' else 'Обработка фотографий'))
                self.details.configure(text=f'Файл: {Path(name).name[:37]}    •    Скорость: {speed_text}    •    Осталось: {"≈ " if not whole and eta is not None else ""}{eta_text}')
            elif kind=='done':
                n,total,errors,cancelled=v;self.export_result=True;self.set_running(False)
                self.status.configure(text=f'{"Отменено" if cancelled else "Готово"}: {n}/{total}. Ошибок: {len(errors)}')
                messagebox.showinfo('Результат',f'Обработано: {n}/{total}\nОшибок: {len(errors)}\nРезультат: {self.target.get()}')
            elif kind=='error':
                self.export_result=True;self.set_running(False);self.status.configure(text='Ошибка экспорта');messagebox.showerror('Ошибка',v)
        if draw_needed and (not self.usb_scanning or time.monotonic()-self.usb_draw_at>1.0):
            self.usb_draw_at=time.monotonic()
            self.draw_tiles()
        self.after(120,self.poll)

if __name__=='__main__':App().mainloop()
