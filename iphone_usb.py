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
    def listdir(self,path):
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
        return result
    def read_to(self,path,destination,progress=None,cancelled=None):
        handle=C.c_uint64()
        self._ok(self.d.afc_file_open(self.afc,path.encode('utf-8'),1,C.byref(handle)),f'Открытие {path}')
        done=0
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
        finally:self.d.afc_file_close(self.afc,handle.value)


class AFCCommandLine:
    """Compatible read-only AFC backend using the confirmed afcclient.exe suite.
    Uses a separate afcclient process per operation. Not as fast as persistent DLL.
    """
    def __init__(self, executable):
        self.executable=str(executable)
        if not Path(self.executable).is_file():
            raise AFCError('afcclient.exe не найден: '+self.executable)
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def listdir(self,path):
        p=subprocess.run([self.executable,'ls',path],capture_output=True,encoding='utf-8',errors='replace',timeout=80,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if p.returncode or 'Error:' in p.stdout or 'Error:' in p.stderr:
            raise AFCError('Не удалось прочитать '+path+': '+(p.stderr or p.stdout)[-400:])
        return [name.strip() for name in p.stdout.splitlines() if name.strip() not in ('','.','..')]
    def read_to(self,path,destination,progress=None,cancelled=None):
        """Retry transient AFC disconnects with a fresh process, never append partial files."""
        destination=Path(destination)
        destination.parent.mkdir(parents=True,exist_ok=True)
        part=destination.with_name(destination.name+'.part')
        attempts=3
        for attempt in range(attempts):
            if cancelled is not None and cancelled.is_set():
                raise InterruptedError('Отменено')
            part.unlink(missing_ok=True)
            process=subprocess.Popen(
                [self.executable,'get',path,str(part)],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                while process.poll() is None:
                    if cancelled is not None and cancelled.is_set():
                        process.terminate()
                        try: process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        raise InterruptedError('Отменено')
                    if progress: progress(part.stat().st_size if part.exists() else 0)
                    time.sleep(.25)
                stdout,stderr=process.communicate(timeout=10)
                output=(stderr or stdout).decode('utf-8','replace')
                disconnected='[disconnected]' in output.lower()
                failed=(process.returncode != 0 or not part.exists()
                        or b'Error:' in stdout or b'Error:' in stderr or disconnected)
                if failed:
                    if disconnected and attempt+1<attempts:
                        # A new afcclient invocation reopens the iPhone connection.
                        # Restart the whole file; never treat a partial as complete.
                        if progress: progress(0)
                        if cancelled is not None and cancelled.wait(1+attempt):
                            raise InterruptedError('Отменено')
                        continue
                    # Only the last lines matter; avoid huge progress spam in reports.
                    detail=output.strip().splitlines()
                    useful=[line.strip() for line in detail if line.strip()
                            and ('disconnect' in line.lower() or 'error' in line.lower())]
                    message=(useful[-1] if useful else (detail[-1] if detail else 'Неизвестная ошибка'))
                    raise AFCError(f'Ошибка копирования {path} (попытка {attempt+1}/{attempts}): {message[:240]}')
                size=part.stat().st_size
                os.replace(part,destination)
                if progress: progress(size)
                return size
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
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


def _media_roots(afc):
    # AFC root corresponds to /var/mobile/Media. Apple may expose DCIM itself
    # or monthly directories. Never assume the Windows Explorer structure maps 1:1.
    root=set(afc.listdir('/'))
    if 'DCIM' in root:return ['/DCIM']
    return ['/']


def _enumerate(afc,cancelled=None):
    stack=_media_roots(afc)
    while stack:
        if cancelled is not None and cancelled.is_set():break
        base=stack.pop()
        for name in afc.listdir(base):
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
