#include "frame_bridge.h"

#include <windows.h>

#include <cstdio>
#include <cstdlib>
#include <string>

namespace
{
    uint32_t ParseDuration(int argc, wchar_t** argv)
    {
        if (argc < 2)
        {
            return 10000;
        }
        wchar_t* end = nullptr;
        const unsigned long value = wcstoul(argv[1], &end, 10);
        if (end == argv[1] || *end != L'\0' || value == 0 || value > 300000)
        {
            return 0;
        }
        return static_cast<uint32_t>(value);
    }
}

int wmain(int argc, wchar_t** argv)
{
    const uint32_t duration_ms = ParseDuration(argc, argv);
    if (duration_ms == 0)
    {
        std::fwprintf(stderr, L"usage: frame_bridge_monitor.exe [duration_ms]\n");
        return 2;
    }

    const ULONGLONG deadline = GetTickCount64() + duration_ms;
    std::unique_ptr<screenbridge::FrameBridge> bridge;
    while (GetTickCount64() < deadline && !bridge)
    {
        bridge = screenbridge::FrameBridge::Open(L"ScreenBridge.Display");
        if (!bridge)
        {
            Sleep(100);
        }
    }
    if (!bridge)
    {
        std::fwprintf(stderr, L"frame bridge not available\n");
        return 1;
    }

    uint64_t first_sequence = 0;
    uint64_t last_sequence = 0;
    uint32_t frame_count = 0;
    uint32_t width = 0;
    uint32_t height = 0;
    uint32_t bytes = 0;
    while (GetTickCount64() < deadline)
    {
        const ULONGLONG remaining_value = deadline - GetTickCount64();
        const DWORD remaining = static_cast<DWORD>(remaining_value > 1000 ? 1000 : remaining_value);
        bridge->Wait(remaining);
        screenbridge::FrameView view;
        if (!bridge->Latest(view) || view.sequence == last_sequence)
        {
            continue;
        }
        if (frame_count == 0)
        {
            first_sequence = view.sequence;
        }
        last_sequence = view.sequence;
        frame_count++;
        width = view.width;
        height = view.height;
        bytes = view.bytes;
    }

    std::wprintf(L"frames=%u first_sequence=%llu last_sequence=%llu width=%u height=%u bytes=%u\n",
                 frame_count,
                 static_cast<unsigned long long>(first_sequence),
                 static_cast<unsigned long long>(last_sequence),
                 width, height, bytes);
    return frame_count > 0 ? 0 : 1;
}
