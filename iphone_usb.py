"""Direct read-only Apple File Conduit (AFC) iPhone media access via libimobiledevice.
No Windows Shell, no file modification on the phone.
DLLs must be installed / bundled separately, with their matching dependencies.
"""
import ctypes as C
import os
import sys
import subprocess
import time
import shutil
import threading
import tempfile
from pathlib import Path, PurePosixPath

EXTS={'.heic','.heif','.jpg','.jpeg','.png','.tif','.tiff','.mov','.mp4','.dng','.aae'}

class AFCError(RuntimeError): pass

class AFC:
    def __init__(self):
        if os.name != 'nt':
            raise AFCError('Прямое USB-подключение предусмотрено для Windows.')
        dll=None
        attempted=[]
        native_dir=(Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent)/'native'
        if native_dir.is_dir() and hasattr(os,'add_dll_directory'):
            self._dll_search=os.add_dll_directory(str(native_dir))
        here=Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
        for filename in ('libimobiledevice-1.0.dll','libimobiledevice.dll'):
            for location in (str(here/'native'/filename), filename):
                try:
                    dll=C.CDLL(location);break
                except OSError as exc:attempted.append(str(exc))
            if dll:break
        if dll is None:
            raise AFCError('Не найдена библиотека libimobiledevice и её зависимости. '
                'Для прямого доступа установи совместимую Windows-сборку libimobiledevice '
                'и положи DLL со всеми зависимостями в папку native рядом с программой. '
                'Понадобится Apple Mobile Device Support. Подробности: README.md')
        self.d=dll
        self._define('idevice_new', [C.POINTER(C.c_void_p), C.c_char_p])
        self._define('idevice_free',[C.c_void_p])
        self._define('lockdownd_client_new_with_handshake',[C.c_void_p,C.POINTER(C.c_void_p),C.c_char_p])
        self._define('lockdownd_client_free',[C.c_void_p])
        self._define('lockdownd_start_service',[C.c_void_p,C.c_char_p,C.POINTER(C.c_void_p)])
        self._define('lockdownd_service_descriptor_free',[C.c_void_p])
        self._define('afc_client_new',[C.c_void_p,C.c_void_p,C.POINTER(C.c_void_p)])
        self._define('afc_client_free',[C.c_void_p])
        self._define('afc_read_directory',[C.c_void_p,C.c_char_p,C.POINTER(C.POINTER(C.c_char_p))])
        self._define('afc_dictionary_free',[C.POINTER(C.c_char_p)])
        self._define('afc_file_open',[C.c_void_p,C.c_char_p,C.c_uint64,C.POINTER(C.c_uint64)])
        self._define('afc_file_read',[C.c_void_p,C.c_uint64,C.c_void_p,C.c_uint32,C.POINTER(C.c_uint32)])
        self._define('afc_file_close',[C.c_void_p,C.c_uint64])
        self.device=C.c_void_p();self.lock=C.c_void_p();self.service=C.c_void_p();self.afc=C.c_void_p()
        try:
            self._ok(self.d.idevice_new(C.byref(self.device),None),'Подключение iPhone')
            self._ok(self.d.lockdownd_client_new_with_handshake(self.device,C.byref(self.lock),b'HushPhoto'),'Доверие iPhone')
            self._ok(self.d.lockdownd_start_service(self.lock,b'com.apple.afc',C.byref(self.service)),'Служба AFC')
            self._ok(self.d.afc_client_new(self.device,self.service,C.byref(self.afc)),'Открытие AFC')
        except Exception:
            self.close();raise
    def _define(self,name,args):
        fn=getattr(self.d,name)
        fn.argtypes=args;fn.restype=C.c_int32
    @staticmethod
    def _ok(code,what):
        if code:raise AFCError(f'{what}: ошибка {code}. Разблокируй iPhone и подтверди доверие компьютеру.')
    def close(self):
        for attr,fn in (('afc','afc_client_free'),('service','lockdownd_service_descriptor_free'),('lock','lockdownd_client_free'),('device','idevice_free')):
            pointer=getattr(self,attr,None)
            if pointer and pointer.value:
                try:getattr(self.d,fn)(pointer)
                except Exception:pass
                setattr(self,attr,C.c_void_p())
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
    def listdir(self,path,cancelled=None):
        if cancelled is not None and cancelled.is_set():raise InterruptedError('Поиск отменён')
        output=C.POINTER(C.c_char_p)()
        code=self.d.afc_read_directory(self.afc,path.encode('utf-8'),C.byref(output))
        self._ok(code,f'Чтение {path}')
        result=[];i=0
        try:
            while output[i]:
                name=output[i].decode('utf-8','replace')
                if name not in ('.','..'): result.append(name)
                i+=1
        finally:self.d.afc_dictionary_free(output)
        if cancelled is not None and cancelled.is_set():raise InterruptedError('Поиск отменён')
        return result
    def read_to(self,path,destination,progress=None,cancelled=None):
        handle=C.c_uint64()
        self._ok(self.d.afc_file_open(self.afc,path.encode('utf-8'),1,C.byref(handle)),f'Открытие {path}')
        done=0
        part=None
        try:
            destination=Path(destination)
            destination.parent.mkdir(parents=True,exist_ok=True)
            part=destination.with_name(destination.name+'.part')
            with open(part,'wb') as out:
                while True:
                    if cancelled is not None and cancelled.is_set():raise InterruptedError('Отменено')
                    buffer=C.create_string_buffer(1024*1024)
                    count=C.c_uint32(0)
                    self._ok(self.d.afc_file_read(self.afc,handle,buffer,len(buffer),C.byref(count)),f'Чтение {path}')
                    if count.value==0:break
                    out.write(buffer.raw[:count.value]);done+=count.value
                    if progress:progress(done)
            os.replace(part,destination)
            return done
        finally:
            try:
                self.d.afc_file_close(self.afc,handle.value)
            finally:
                if part is not None:
                    part.unlink(missing_ok=True)


class AFCCommandLine:
    """Compatible read-only AFC backend using the confirmed afcclient.exe suite.
    Uses a separate afcclient process per operation. Not as fast as persistent DLL.
    """
    def __init__(self, executable):
        self.executable=str(executable)
        if not Path(self.executable).is_file():
            raise AFCError('afcclient.exe не найден: '+self.executable)
        self.device_tool=Path(self.executable).with_name('idevice_id.exe')
        self._last_probe=0.0
        self._initial_devices=None
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def _ensure_connected(self,cancelled=None):
        """Detect unplugged phones when idevice_id is bundled with afcclient."""
        if cancelled is not None and cancelled.is_set():
            raise InterruptedError('Поиск отменён')
        if not self.device_tool.is_file():
            return  # AFC ls still detects I/O failures on its own.
        now=time.monotonic()
        if self._initial_devices is not None and now-self._last_probe < 2:
            return
        try:
            proc=subprocess.run(
                [str(self.device_tool),'-l'],capture_output=True,
                timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired as exc:
            raise AFCError('iPhone не отвечает. Проверь USB-кабель и разблокировку.') from exc
        if proc.returncode:
            raise AFCError('Не удалось проверить подключение iPhone (idevice_id).')
        present={line.strip() for line in proc.stdout.decode('utf-8','replace').splitlines()
                 if line.strip()}
        if not present or (self._initial_devices is not None and not (present & self._initial_devices)):
            raise AFCError('iPhone отключён. Подключи устройство и повтори поиск.')
        if self._initial_devices is None:
            self._initial_devices=present
        self._last_probe=time.monotonic()
        if cancelled is not None and cancelled.is_set():
            raise InterruptedError('Поиск отменён')

    def listdir(self,path,cancelled=None):
        """Never block the UI on a stalled AFC directory listing indefinitely.

        A file redirect avoids PIPE deadlock for very large DCIM directory listings.
        """
        self._ensure_connected(cancelled)
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process=subprocess.Popen(
                [self.executable,'ls',path],stdin=subprocess.DEVNULL,
                stdout=stdout,stderr=stderr,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            started=time.monotonic()
            try:
                while process.poll() is None:
                    if cancelled is not None and cancelled.is_set():
                        raise InterruptedError('Поиск отменён')
                    if time.monotonic()-started > 20:
                        raise AFCError('iPhone перестал отвечать при чтении '+path+'. Проверь подключение.')
                    time.sleep(.15)
                stdout.seek(0);stderr.seek(0)
                output=stdout.read().decode('utf-8','replace')
                errors=stderr.read().decode('utf-8','replace')
                combined=(output+'\n'+errors).lower()
                if (process.returncode or 'error:' in combined
                        or 'disconnected' in combined or 'not connected' in combined):
                    raise AFCError('Не удалось прочитать '+path+': '+(errors or output)[-400:])
                if cancelled is not None and cancelled.is_set():
                    raise InterruptedError('Поиск отменён')
                return [name.strip() for name in output.splitlines()
                        if name.strip() not in ('','.','..')]
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill();process.wait()

    def read_to(self,path,destination,progress=None,cancelled=None):
        """Retry disconnects; bound idle time and avoid child stdout pipe deadlocks."""
        destination=Path(destination)
        destination.parent.mkdir(parents=True,exist_ok=True)
        part=destination.with_name(destination.name+'.part')
        attempts=3
        for attempt in range(attempts):
            if cancelled is not None and cancelled.is_set():
                raise InterruptedError('Отменено')
            part.unlink(missing_ok=True)
            with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
                process=subprocess.Popen(
                    [self.executable,'get',path,str(part)],
                    stdin=subprocess.DEVNULL,stdout=stdout_file,stderr=stderr_file,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                last_progress=time.monotonic()
                previous_size=0
                try:
                    while process.poll() is None:
                        if cancelled is not None and cancelled.is_set():
                            raise InterruptedError('Отменено')
                        size=part.stat().st_size if part.exists() else 0
                        if size>previous_size:
                            previous_size=size
                            last_progress=time.monotonic()
                        if time.monotonic()-last_progress>45:
                            raise AFCError('iPhone не отвечает при копировании '+path+
                                           '. Проверь USB-кабель и повтори экспорт.')
                        if progress:progress(size)
                        time.sleep(.25)
                    stdout_file.seek(0);stderr_file.seek(0)
                    stdout=stdout_file.read();stderr=stderr_file.read()
                    output=(stderr or stdout).decode('utf-8','replace')
                    disconnected='disconnected' in output.lower()
                    failed=(process.returncode != 0 or not part.exists()
                            or b'error:' in stdout.lower() or b'error:' in stderr.lower()
                            or disconnected)
                    if failed:
                        if disconnected and attempt+1<attempts:
                            if progress:progress(0)
                            if cancelled is not None and cancelled.wait(1+attempt):
                                raise InterruptedError('Отменено')
                            continue
                        detail=output.strip().splitlines()
                        useful=[line.strip() for line in detail if line.strip()
                                and ('disconnect' in line.lower() or 'error' in line.lower())]
                        message=(useful[-1] if useful else (detail[-1] if detail else 'Неизвестная ошибка'))
                        raise AFCError(f'Ошибка копирования {path} (попытка {attempt+1}/{attempts}): {message[:240]}')
                    size=part.stat().st_size
                    os.replace(part,destination)
                    if progress:progress(size)
                    return size
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill();process.wait()
                    part.unlink(missing_ok=True)


def _afc_executable():
    base=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    locations=[base/'native'/'afcclient.exe',base/'afcclient.exe']
    configured=os.environ.get('HUSH_AFC_TOOLS','')
    if configured:locations.insert(0,Path(configured)/'afcclient.exe')
    found=shutil.which('afcclient.exe')
    if found:locations.append(Path(found))
    return next((p for p in locations if p.is_file()),None)


def open_afc():
    # Prefer an explicitly configured or bundled afcclient over an untested DLL ABI.
    exe=_afc_executable()
    if exe:return AFCCommandLine(exe)
    try:return AFC()
    except (AFCError,OSError,AttributeError) as e:
        raise AFCError(str(e)+'\nНе найден afcclient.exe. Укажи HUSH_AFC_TOOLS '
                       'или положи набор утилит в папку native.') from e


def _media_roots(afc,cancelled=None):
    # AFC root corresponds to /var/mobile/Media. Apple may expose DCIM itself
    # or monthly directories. Never assume the Windows Explorer structure maps 1:1.
    root=set(afc.listdir('/',cancelled=cancelled))
    if 'DCIM' in root:return ['/DCIM']
    return ['/']


def _enumerate(afc,cancelled=None):
    stack=_media_roots(afc,cancelled)
    while stack:
        if cancelled is not None and cancelled.is_set():break
        base=stack.pop()
        for name in afc.listdir(base,cancelled=cancelled):
            if cancelled is not None and cancelled.is_set():
                raise InterruptedError('Поиск отменён')
            path=base.rstrip('/')+'/'+name
            extension=Path(name).suffix.lower()
            if extension in EXTS:
                yield {'path':path.lstrip('/'),'name':name,'size':None,'suffix':extension}
            elif '.' not in name and (base != '/' or name == 'DCIM' or (len(name)>=6 and name[:6].isdigit())):
                stack.append(path)


def list_iphone_media(on_batch=None,cancelled=None,batch_size=64):
    with open_afc() as afc:
        result=[];batch=[]
        for row in _enumerate(afc,cancelled):
            result.append(row);batch.append(row)
            if len(batch)>=batch_size:
                if on_batch:on_batch(batch,len(result))
                batch=[]
        if cancelled is not None and cancelled.is_set():
            raise InterruptedError('Поиск отменён')
        if batch and on_batch:on_batch(batch,len(result))
        return result


def copy_from_iphone(target,progress,cancelled,selected_paths=None):
    target=Path(target)
    with open_afc() as afc:
        paths=sorted(selected_paths) if selected_paths is not None else [x['path'] for x in _enumerate(afc,cancelled)]
        failures=[];done_files=0;done_bytes=0
        for path in paths:
            if cancelled.is_set():break
            # Guard against malformed/hostile relative paths.
            p=PurePosixPath(path)
            if p.is_absolute() or '..' in p.parts:failures.append(f'{path}: путь отклонён');continue
            dest=target.joinpath(*p.parts)
            try:
                progress(done_bytes,0,path,done_files,len(paths))
                added=afc.read_to('/'+path.lstrip('/'),dest,lambda count:progress(done_bytes+count,0,path,done_files,len(paths)),cancelled)
                done_bytes+=added;done_files+=1
                progress(done_bytes,0,path,done_files,len(paths))
            except InterruptedError:break
            except Exception as exc:failures.append(f'{path}: {exc}')
        return done_files,len(paths),failures,cancelled.is_set()


def selected_with_live_pairs(items,selected,include_mov=True):
    by_path={x['path'] for x in items};selected=set(selected)
    if include_mov:
        for key in list(selected):
            p=PurePosixPath(key)
            if p.suffix.lower() in {'.heic','.heif','.jpg','.jpeg','.dng'}:
                for entry in by_path:
                    peer=PurePosixPath(entry)
                    if peer.parent==p.parent and peer.stem.casefold()==p.stem.casefold() and peer.suffix.lower()=='.mov':selected.add(entry)
    return selected
