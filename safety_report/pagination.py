"""Local Writer pagination via its built-in UNO/Basic engine, in an isolated profile.
No bundled Python executable, remote service, office process sharing or security-setting changes.
"""
import os,re,shutil,signal,subprocess,tempfile,zipfile
from pathlib import Path
from xml.sax.saxutils import escape


def find_engine():
    configured=os.environ.get('SAFETY_OFFICE_PATH')
    if configured:return str(Path(configured)) if Path(configured).is_file() else None
    candidates=[shutil.which('soffice'),shutil.which('libreoffice'),'/Applications/LibreOffice.app/Contents/MacOS/soffice']
    for root in (os.environ.get('PROGRAMFILES'),os.environ.get('PROGRAMFILES(X86)')):
        if root:candidates.append(str(Path(root)/'LibreOffice/program/soffice.exe'))
    return next((str(c) for c in candidates if c and Path(c).is_file()),None)


def _basic_string(value):return '"'+str(value).replace('"','""')+'"'


def _install_macro(profile,source,output,pdf,result):
    folder=profile/'user/basic/Standard';folder.mkdir(parents=True,exist_ok=True)
    (folder/'script.xlb').write_text('<library:library xmlns:library="http://openoffice.org/2000/library" library:name="Standard" library:readonly="false" library:passwordprotected="false"><library:element library:name="Pagination"/></library:library>',encoding='utf-8')
    code='''Sub Run
On Error GoTo Failed
Dim doc As Object, indexes As Object, cursor As Object
Dim loadOptions(2) As New com.sun.star.beans.PropertyValue
Dim saveOptions(1) As New com.sun.star.beans.PropertyValue
Dim pdfOptions(1) As New com.sun.star.beans.PropertyValue
Dim pass As Integer, idx As Integer, pages As Long, n As Integer
loadOptions(0).Name="Hidden": loadOptions(0).Value=True
loadOptions(1).Name="MacroExecutionMode": loadOptions(1).Value=0
loadOptions(2).Name="UpdateDocMode": loadOptions(2).Value=0
doc=StarDesktop.loadComponentFromURL(SOURCE_URL,"_blank",0,loadOptions())
doc.CurrentController.ViewSettings.ShowOnlineLayout=False
For pass=1 To 3
 doc.TextFields.refresh()
 indexes=doc.DocumentIndexes
 For idx=0 To indexes.Count-1
  indexes.getByIndex(idx).update()
 Next idx
 doc.refresh()
 cursor=doc.CurrentController.ViewCursor
 cursor.jumpToLastPage()
 pages=cursor.Page
Next pass
saveOptions(0).Name="FilterName": saveOptions(0).Value="Office Open XML Text"
saveOptions(1).Name="Overwrite": saveOptions(1).Value=True
doc.storeAsURL(OUTPUT_URL,saveOptions())
pdfOptions(0).Name="FilterName": pdfOptions(0).Value="writer_pdf_Export"
pdfOptions(1).Name="Overwrite": pdfOptions(1).Value=True
doc.storeToURL(PDF_URL,pdfOptions())
doc.close(True)
n=FreeFile
Open RESULT_PATH For Output As #n
Print #n,"OK " & pages
Close #n
StarDesktop.terminate()
Exit Sub
Failed:
n=FreeFile
Open RESULT_PATH For Output As #n
Print #n,"ERROR " & Err & " " & Error$
Close #n
On Error Resume Next
doc.close(True)
StarDesktop.terminate()
End Sub'''
    for token,value in [('SOURCE_URL',source.as_uri()),('OUTPUT_URL',output.as_uri()),('PDF_URL',pdf.as_uri()),('RESULT_PATH',str(result))]:code=code.replace(token,_basic_string(value))
    module='<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Pagination" script:language="StarBasic">'+escape(code)+'</script:module>'
    (folder/'Pagination.xba').write_text(module,encoding='utf-8')


def _run(command,env,timeout):
    options={'stdout':subprocess.PIPE,'stderr':subprocess.PIPE,'env':env}
    if os.name=='nt':options['creationflags']=subprocess.CREATE_NEW_PROCESS_GROUP
    else:options['start_new_session']=True
    process=subprocess.Popen(command,**options)
    try:
        stdout,stderr=process.communicate(timeout=timeout)
        if process.returncode:raise subprocess.CalledProcessError(process.returncode,command,output=stdout,stderr=stderr)
    except subprocess.TimeoutExpired:
        if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10)
        else:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        process.communicate(timeout=10)
        raise


def _finish_docx_view(path):
    # Writer omits its default print-view flag; Word may otherwise reuse a previous Web Layout view.
    pending=path.with_name(path.name+'.view.tmp')
    with zipfile.ZipFile(path) as source,zipfile.ZipFile(pending,'w') as target:
        for item in source.infolist():
            data=source.read(item.filename)
            if item.filename=='word/settings.xml':
                text=data.decode('utf-8')
                for tag,value in [('view','print'),('updateFields','false')]:
                    replacement='<w:'+tag+' w:val="'+value+'"/>'
                    if re.search(r'<w:'+tag+r'\b[^>]*/>',text):text=re.sub(r'<w:'+tag+r'\b[^>]*/>',replacement,text)
                    else:text=re.sub(r'(<w:settings\b[^>]*>)',lambda m:m.group(1)+replacement,text,count=1)
                data=text.encode('utf-8')
            target.writestr(item,data)
    pending.replace(path)


def paginate(path,required=False,force=False):
    if not force and os.environ.get('SAFETY_PAGINATION_MODE')=='off':return {'status':'disabled','note':'本次运行未执行排版'}
    engine=find_engine()
    if not engine:
        if required:raise ValueError('本机尚未配置文档排版组件，不能生成带真实目录页码的总稿；请安装LibreOffice后重试')
        return {'status':'unavailable','note':'尚未完成真实分页，目录需在配置排版组件后重新保存'}
    path=Path(path).resolve()
    with tempfile.TemporaryDirectory(prefix='safety-pagination-') as folder:
        temp=Path(folder);profile=temp/'profile';output=temp/'paginated.docx';pdf=temp/'report.pdf';result=temp/'result.txt'
        env={**os.environ,'XDG_CACHE_HOME':str(temp/'cache')};(temp/'cache').mkdir()
        if Path('/System/Library/Fonts').is_dir():
            fontconf=temp/'fonts.conf'
            directories=['/System/Library/Fonts','/System/Library/Fonts/Supplemental','/Library/Fonts',str(Path.home()/'Library/Fonts')]
            fontconf.write_text('<fontconfig>'+''.join('<dir>'+escape(d)+'</dir>' for d in directories)+'<cachedir>'+escape(str(temp/'cache'))+'</cachedir><alias><family>宋体</family><prefer><family>Songti SC</family><family>Noto Serif CJK SC</family></prefer></alias><alias><family>黑体</family><prefer><family>Heiti SC</family><family>PingFang SC</family></prefer></alias></fontconfig>',encoding='utf-8')
            env['FONTCONFIG_FILE']=str(fontconf)
        command=[engine,'-env:UserInstallation='+profile.as_uri(),'--headless','--nologo','--norestore']
        try:
            # First startup creates the default Standard library, so initialise before installing our entry point.
            _run(command+['--terminate_after_init'],env,30)
            _install_macro(profile,path,output,pdf,result)
            _run(command+['macro:///Standard.Pagination.Run()'],env,240)
            status=result.read_text(encoding='utf-8').strip() if result.exists() else ''
            if not status.startswith('OK ') or not output.is_file() or not pdf.is_file():raise ValueError('文档排版未完成，原文件保留；请检查排版组件和文档格式')
            with zipfile.ZipFile(output) as archive:
                if 'word/document.xml' not in archive.namelist():raise ValueError('排版组件未输出有效Word，原文件保留')
            from pypdf import PdfReader
            pages=len(PdfReader(pdf).pages)
            if pages<1:raise ValueError('排版输出没有有效页面，原文件保留')
            # Preserve original bytes on any engine failure; replace only after both files have been validated.
            _finish_docx_view(output)
            pending=path.with_name('.'+path.name+'.paginated');shutil.copyfile(output,pending);pending.replace(path)
            shutil.copyfile(pdf,path.with_suffix('.pdf'))
            return {'status':'completed','engine':'LibreOffice Writer','page_count':pages,'toc_updated':True,'pdf_ready':True}
        except subprocess.TimeoutExpired:raise ValueError('文档排版超时，原文件和已有版本保留，请重试或检查排版组件') from None
        except (zipfile.BadZipFile,OSError):raise ValueError('排版输出无法读取，原文件和已有版本保留') from None
        except subprocess.CalledProcessError:raise ValueError('文档排版组件运行失败，原文件和已有版本保留') from None
