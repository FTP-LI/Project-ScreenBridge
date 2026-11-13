#include "frame_bridge.h"

#include <sddl.h>

#include <algorithm>
#include <cstring>
#include <limits>
#include <utility>

#pragma comment(lib, "advapi32.lib")

namespace screenbridge
{
    namespace
    {
        constexpr DWORD kCreateFileMappingErrorAlreadyExists = 183;
        constexpr DWORD kPageReadWrite = 0x04;
        constexpr DWORD kMapRead = 0x0004;
        constexpr DWORD kMapWrite = 0x0002;
        constexpr DWORD kEventModifyState = 0x0002;
        constexpr DWORD kSync = 0x00100000;

        bool ValidDimensions(uint32_t width, uint32_t height, uint32_t stride,
                             uint32_t bytes, uint32_t capacity)
        {
            if (width == 0 || height == 0 || stride < width || bytes > capacity)
            {
                return false;
            }
            if (height > std::numeric_limits<uint32_t>::max() / stride)
            {
                return false;
            }
            return bytes == stride * height;
        }
    }

    std::wstring FrameBridge::MappingName(const std::wstring& name)
    {
        if (name.rfind(L"Local\\", 0) == 0 || name.rfind(L"Global\\", 0) == 0)
        {
            return name + L".mapping";
        }
        return L"Global\\ScreenBridge.Frame." + name;
    }

    std::wstring FrameBridge::EventName(const std::wstring& name)
    {
        if (name.rfind(L"Local\\", 0) == 0 || name.rfind(L"Global\\", 0) == 0)
        {
            return name + L".event";
        }
        return L"Global\\ScreenBridge.FrameEvent." + name;
    }

    bool FrameBridge::CreateSecurityAttributes(SECURITY_ATTRIBUTES& attributes, PVOID& descriptor)
    {
        // SYSTEM and administrators get full access; interactive users get
        // read/write access. The descriptor is freed by the caller.
        const wchar_t* sddl = L"D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GA;;;AU)";
        descriptor = nullptr;
        if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl, SDDL_REVISION_1,
                reinterpret_cast<PSECURITY_DESCRIPTOR*>(&descriptor), nullptr))
        {
            return false;
        }
        attributes.nLength = sizeof(attributes);
        attributes.lpSecurityDescriptor = descriptor;
        attributes.bInheritHandle = FALSE;
        return true;
    }

    FrameBridge::FrameBridge(HANDLE mapping, HANDLE event, void* view, uint32_t capacity)
        : mapping_(mapping), event_(event), view_(view), capacity_(capacity)
    {
        InitializeCriticalSection(&lock_);
    }

    FrameBridge::~FrameBridge()
    {
        Close();
        DeleteCriticalSection(&lock_);
    }

    std::unique_ptr<FrameBridge> FrameBridge::Create(const std::wstring& name, uint32_t capacity)
    {
        if (name.empty() || capacity == 0)
        {
            return nullptr;
        }
        SECURITY_ATTRIBUTES attributes{};
        PVOID descriptor = nullptr;
        if (!CreateSecurityAttributes(attributes, descriptor))
        {
            return nullptr;
        }
        const uint64_t total = sizeof(SharedFrameHeader) + capacity;
        if (total > std::numeric_limits<DWORD>::max())
        {
            LocalFree(descriptor);
            return nullptr;
        }
        HANDLE mapping = CreateFileMappingW(
            INVALID_HANDLE_VALUE, &attributes, kPageReadWrite,
            0, static_cast<DWORD>(total), MappingName(name).c_str());
        const DWORD mapping_error = GetLastError();
        HANDLE event = CreateEventW(&attributes, FALSE, FALSE, EventName(name).c_str());
        LocalFree(descriptor);
        if (!mapping || !event || mapping_error == kCreateFileMappingErrorAlreadyExists)
        {
            if (event) CloseHandle(event);
            if (mapping) CloseHandle(mapping);
            return nullptr;
        }
        void* view = MapViewOfFile(mapping, kMapRead | kMapWrite, 0, 0, total);
        if (!view)
        {
            CloseHandle(event);
            CloseHandle(mapping);
            return nullptr;
        }
        auto bridge = std::unique_ptr<FrameBridge>(new FrameBridge(mapping, event, view, capacity));
        auto* header = static_cast<SharedFrameHeader*>(view);
        ZeroMemory(header, sizeof(*header));
        header->magic = kFrameBridgeMagic;
        header->version = kFrameBridgeVersion;
        header->capacity = capacity;
        return bridge;
    }

    std::unique_ptr<FrameBridge> FrameBridge::Open(const std::wstring& name)
    {
        if (name.empty())
        {
            return nullptr;
        }
        HANDLE mapping = OpenFileMappingW(kMapRead, FALSE, MappingName(name).c_str());
        if (!mapping)
        {
            return nullptr;
        }
        HANDLE event = OpenEventW(kSync, FALSE, EventName(name).c_str());
        if (!event)
        {
            CloseHandle(mapping);
            return nullptr;
        }
        void* view = MapViewOfFile(mapping, kMapRead, 0, 0, 0);
        if (!view)
        {
            CloseHandle(event);
            CloseHandle(mapping);
            return nullptr;
        }
        auto* header = static_cast<SharedFrameHeader*>(view);
        if (header->magic != kFrameBridgeMagic || header->version != kFrameBridgeVersion || header->capacity == 0)
        {
            UnmapViewOfFile(view);
            CloseHandle(event);
            CloseHandle(mapping);
            return nullptr;
        }
        return std::unique_ptr<FrameBridge>(new FrameBridge(mapping, event, view, header->capacity));
    }

    uint32_t FrameBridge::Checksum(const uint8_t* data, uint32_t bytes)
    {
        uint32_t crc = 0xFFFFFFFFu;
        for (uint32_t index = 0; index < bytes; ++index)
        {
            crc ^= data[index];
            for (int bit = 0; bit < 8; ++bit)
            {
                const uint32_t mask = 0u - (crc & 1u);
                crc = (crc >> 1) ^ (0xEDB88320u & mask);
            }
        }
        return crc ^ 0xFFFFFFFFu;
    }

    bool FrameBridge::Publish(uint32_t width, uint32_t height, uint32_t stride,
                              const uint8_t* data, uint32_t bytes)
    {
        if (data == nullptr || !ValidDimensions(width, height, stride, bytes, capacity_))
        {
            return false;
        }
        EnterCriticalSection(&lock_);
        if (closed_)
        {
            LeaveCriticalSection(&lock_);
            return false;
        }
        auto* header = static_cast<SharedFrameHeader*>(view_);
        InterlockedIncrement64(&header->sequence);
        uint8_t* payload = reinterpret_cast<uint8_t*>(header + 1);
        std::memcpy(payload, data, bytes);
        header->width = width;
        header->height = height;
        header->stride = stride;
        header->bytes = bytes;
        header->crc32 = Checksum(data, bytes);
        MemoryBarrier();
        InterlockedIncrement64(&header->sequence);
        SetEvent(event_);
        LeaveCriticalSection(&lock_);
        return true;
    }

    bool FrameBridge::Latest(FrameView& out) const
    {
        EnterCriticalSection(&lock_);
        if (closed_)
        {
            LeaveCriticalSection(&lock_);
            return false;
        }
        const auto* header = static_cast<const SharedFrameHeader*>(view_);
        const LONG64 first = header->sequence;
        if (first == 0 || (first & 1) != 0 || header->bytes > capacity_)
        {
            LeaveCriticalSection(&lock_);
            return false;
        }
        const uint8_t* payload = reinterpret_cast<const uint8_t*>(header + 1);
        FrameView candidate;
        candidate.sequence = static_cast<uint64_t>(first);
        candidate.width = header->width;
        candidate.height = header->height;
        candidate.stride = header->stride;
        candidate.bytes = header->bytes;
        candidate.payload.assign(payload, payload + header->bytes);
        const uint32_t crc = Checksum(candidate.payload.data(), candidate.bytes);
        const LONG64 second = header->sequence;
        const uint32_t final_crc = header->crc32;
        LeaveCriticalSection(&lock_);
        if (first != second || (second & 1) != 0 || crc != final_crc)
        {
            return false;
        }
        out = std::move(candidate);
        return true;
    }

    bool FrameBridge::Wait(uint32_t timeout_ms) const
    {
        if (closed_ || !event_)
        {
            return false;
        }
        const DWORD result = WaitForSingleObject(event_, timeout_ms);
        return result == WAIT_OBJECT_0;
    }

#ifdef SCREENBRIDGE_TESTING
    void FrameBridge::CorruptChecksumForTest()
    {
        EnterCriticalSection(&lock_);
        if (!closed_)
        {
            auto* header = static_cast<SharedFrameHeader*>(view_);
            header->crc32 ^= 1u;
        }
        LeaveCriticalSection(&lock_);
    }
#endif

    void FrameBridge::Close()
    {
        EnterCriticalSection(&lock_);
        if (closed_)
        {
            LeaveCriticalSection(&lock_);
            return;
        }
        closed_ = true;
        void* view = view_;
        HANDLE event = event_;
        HANDLE mapping = mapping_;
        view_ = nullptr;
        event_ = nullptr;
        mapping_ = nullptr;
        LeaveCriticalSection(&lock_);
        if (view) UnmapViewOfFile(view);
        if (event) CloseHandle(event);
        if (mapping) CloseHandle(mapping);
    }
}
