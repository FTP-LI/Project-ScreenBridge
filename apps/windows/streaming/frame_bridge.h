#pragma once

#define NOMINMAX
#include <windows.h>

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace screenbridge
{
    constexpr uint32_t kFrameBridgeMagic = 0x31464253u; // "SBF1"
    constexpr uint32_t kFrameBridgeVersion = 1;

    // This layout is shared by the user process and the future IDD producer.
    // sequence is even for a stable frame and odd while a producer is writing.
    struct SharedFrameHeader
    {
        uint32_t magic;
        uint32_t version;
        uint32_t capacity;
        volatile LONG64 sequence;
        uint32_t width;
        uint32_t height;
        uint32_t stride;
        uint32_t bytes;
        uint32_t crc32;
    };

    struct FrameView
    {
        uint64_t sequence = 0;
        uint32_t width = 0;
        uint32_t height = 0;
        uint32_t stride = 0;
        uint32_t bytes = 0;
        std::vector<uint8_t> payload;
    };

    class FrameBridge
    {
    public:
        static std::unique_ptr<FrameBridge> Create(const std::wstring& name, uint32_t capacity);
        static std::unique_ptr<FrameBridge> Open(const std::wstring& name);
        ~FrameBridge();

        FrameBridge(const FrameBridge&) = delete;
        FrameBridge& operator=(const FrameBridge&) = delete;

        bool Publish(uint32_t width, uint32_t height, uint32_t stride,
                     const uint8_t* data, uint32_t bytes);
        bool Latest(FrameView& out) const;
        bool Wait(uint32_t timeout_ms) const;
        void Close();

#ifdef SCREENBRIDGE_TESTING
        void CorruptChecksumForTest();
#endif

    private:
        FrameBridge(HANDLE mapping, HANDLE event, void* view, uint32_t capacity);
        static std::unique_ptr<FrameBridge> MapExisting(HANDLE mapping, HANDLE event);
        static uint32_t Checksum(const uint8_t* data, uint32_t bytes);
        static std::wstring MappingName(const std::wstring& name);
        static std::wstring EventName(const std::wstring& name);
        static bool CreateSecurityAttributes(SECURITY_ATTRIBUTES& attributes, PVOID& descriptor);

        HANDLE mapping_ = nullptr;
        HANDLE event_ = nullptr;
        void* view_ = nullptr;
        uint32_t capacity_ = 0;
        mutable CRITICAL_SECTION lock_;
        bool closed_ = false;
    };
}
