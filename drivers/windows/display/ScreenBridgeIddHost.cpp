#include <windows.h>
#include <swdevice.h>
#include <stdio.h>

static VOID WINAPI CreationCallback(HSWDEVICE, HRESULT, PVOID context, PCWSTR)
{
    SetEvent(*static_cast<HANDLE*>(context));
}

int wmain(int argc, wchar_t** argv)
{
    if (argc < 2)
    {
        wprintf(L"usage: ScreenBridgeIddHost.exe <stop-file>\n");
        return 2;
    }

    HANDLE created = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    if (created == nullptr)
    {
        return 1;
    }

    SW_DEVICE_CREATE_INFO info = {};
    info.cbSize = sizeof(info);
    info.pszInstanceId = L"ScreenBridgeIdd";
    info.pszzHardwareIds = L"ScreenBridgeIdd\0\0";
    info.pszzCompatibleIds = L"ScreenBridgeIdd\0\0";
    info.pszDeviceDescription = L"ScreenBridge Display";
    info.CapabilityFlags = SWDeviceCapabilitiesRemovable |
                           SWDeviceCapabilitiesSilentInstall |
                           SWDeviceCapabilitiesDriverRequired;

    HSWDEVICE device = nullptr;
    HRESULT hr = SwDeviceCreate(L"ScreenBridgeIdd", L"HTREE\\ROOT\\0", &info, 0, nullptr,
                                CreationCallback, &created, &device);
    if (FAILED(hr))
    {
        wprintf(L"SwDeviceCreate failed: 0x%08lx\n", hr);
        return 1;
    }

    if (WaitForSingleObject(created, 10000) != WAIT_OBJECT_0)
    {
        wprintf(L"device creation timed out\n");
        SwDeviceClose(device);
        return 1;
    }
    wprintf(L"device created\n");

    while (GetFileAttributesW(argv[1]) == INVALID_FILE_ATTRIBUTES)
    {
        Sleep(200);
    }
    SwDeviceClose(device);
    wprintf(L"device removed\n");
    return 0;
}
