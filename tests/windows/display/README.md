# G3 帧桥测试

用户态 producer-consumer 回归：

```powershell
cmd /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" && cl /nologo /std:c++17 /EHsc /W4 /DSCREENBRIDGE_TESTING /I. /Iapps\windows\streaming /Fe:work\frame_bridge_test.exe tests\windows\display\frame_bridge_test.cpp apps\windows\streaming\frame_bridge.cpp advapi32.lib && work\frame_bridge_test.exe'
```

标准用户监视器用于 IDD 宿主创建的 `Global\\ScreenBridge.Display`：

```powershell
cmd /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" && cl /nologo /std:c++17 /EHsc /W4 /I. /Iapps\windows\streaming /Fe:work\frame_bridge_monitor.exe apps\windows\streaming\frame_bridge_monitor.cpp apps\windows\streaming\frame_bridge.cpp advapi32.lib && work\frame_bridge_monitor.exe 10000'
```

监视器返回 `frames=...` 且退出码 0 才算读到至少一帧；退出码 1 表示宿主没有创建共享段或没有发布帧。它不会创建 `Global` 对象，也不会替代显示拓扑验收。
