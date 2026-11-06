@echo on
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b 1
set MSVC=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207
set KIT=C:\Program Files (x86)\Windows Kits\10
cl /nologo /c /std:c++17 /EHsc /MD /W3 /DUNICODE /D_UNICODE /D_WIN64 /D_AMD64_ /DAMD64 /DUMDF_DRIVER /DUMDF_VERSION_MAJOR=2 /DUMDF_VERSION_MINOR=25 /DIDDCX_VERSION_MAJOR=1 /DIDDCX_VERSION_MINOR=6 /DIDDCX_MINIMUM_VERSION_REQUIRED=4 /I"%MSVC%\include" /I"%KIT%\Include\10.0.26100.0\um" /I"%KIT%\Include\10.0.26100.0\shared" /I"%KIT%\Include\10.0.26100.0\ucrt" /I"%KIT%\Include\wdf\umdf\2.25" /I"%KIT%\Include\10.0.26100.0\um\iddcx\1.6" /FoDriver.obj Driver.cpp
if errorlevel 1 exit /b 1
link /nologo /DLL /MAP:ScreenBridgeIdd.map /SUBSYSTEM:WINDOWS /OUT:ScreenBridgeIdd.dll /MERGE:.kmdfclassbind=.data /INCLUDE:?__KMDF_CLASS_BIND_START@@3U_MARKER_TYPE@@A /INCLUDE:?__KMDF_CLASS_BIND_END@@3PEAXEA /LIBPATH:"%MSVC%\lib\x64" /LIBPATH:"%KIT%\Lib\10.0.26100.0\um\x64" /LIBPATH:"%KIT%\Lib\10.0.26100.0\ucrt\x64" /LIBPATH:"%KIT%\Lib\wdf\umdf\x64\2.25" /LIBPATH:"%KIT%\Lib\10.0.26100.0\um\x64\iddcx\1.6" Driver.obj WdfDriverStubUm.lib iddcxstub.lib OneCoreUAP.lib avrt.lib ntdll.lib wpprecorderum.lib
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /W3 /DUNICODE /D_UNICODE /Fe:ScreenBridgeIddHost.exe ScreenBridgeIddHost.cpp swdevice.lib
exit /b %ERRORLEVEL%
