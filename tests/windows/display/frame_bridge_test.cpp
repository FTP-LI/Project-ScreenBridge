#include "../../../apps/windows/streaming/frame_bridge.h"

#include <windows.h>

#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

static void expect(bool condition, const char* message)
{
    if (!condition)
    {
        std::fputs(message, stderr);
        std::fputc('\n', stderr);
        std::exit(1);
    }
}

int main()
{
    const std::wstring name = L"Local\\ScreenBridge.g3-test-" + std::to_wstring(GetCurrentProcessId());
    auto producer = screenbridge::FrameBridge::Create(name, 64);
    expect(producer != nullptr, "producer bridge should create");
    auto consumer = screenbridge::FrameBridge::Open(name);
    expect(consumer != nullptr, "consumer bridge should open");

    screenbridge::FrameView view;
    expect(!consumer->Latest(view), "empty bridge should have no frame");

    const uint8_t first[] = {1, 2, 3, 4};
    expect(producer->Publish(2, 2, 2, first, sizeof(first)), "first frame should publish");
    expect(consumer->Wait(1000), "consumer should observe the frame event");
    expect(consumer->Latest(view), "consumer should read first frame");
    expect(view.width == 2 && view.height == 2 && view.stride == 2 && view.bytes == 4, "first frame metadata");
    expect(view.payload == std::vector<uint8_t>({1, 2, 3, 4}), "first frame payload");

    const uint8_t second[] = {9, 8, 7, 6, 5, 4};
    expect(producer->Publish(3, 2, 3, second, sizeof(second)), "second frame should replace first");
    expect(consumer->Latest(view), "consumer should read latest frame");
    expect(view.sequence > 0 && view.payload == std::vector<uint8_t>({9, 8, 7, 6, 5, 4}), "latest payload");

    producer->CorruptChecksumForTest();
    expect(!consumer->Latest(view), "CRC corruption must reject the frame");

    expect(!producer->Publish(0, 1, 1, second, 1), "zero width rejected");
    expect(!producer->Publish(3, 2, 3, second, 5), "short payload rejected");
    expect(!producer->Publish(9, 9, 9, second, sizeof(second)), "capacity rejected");

    producer->Close();
    producer->Close();
    consumer->Close();
    consumer->Close();
    return 0;
}
