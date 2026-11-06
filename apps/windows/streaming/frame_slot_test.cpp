#include "frame_slot.h"

#include <cstdio>
#include <cstdlib>
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
    FrameSlot slot(16);
    std::vector<uint8_t> out;
    uint32_t sequence = 0;
    uint32_t width = 0;
    uint32_t height = 0;
    uint32_t stride = 0;
    expect(!slot.latest(out, sequence, width, height, stride), "empty slot must not return a frame");

    const uint8_t first[] = {1, 2, 3, 4};
    expect(slot.publish(2, 2, 2, first, 4), "first frame should publish");
    expect(slot.latest(out, sequence, width, height, stride), "first frame should be readable");
    expect(sequence == 1 && width == 2 && height == 2 && stride == 2 && out.size() == 4 && out[0] == 1, "first frame fields");

    const uint8_t second[] = {9, 8, 7, 6, 5, 4};
    expect(slot.publish(3, 2, 3, second, 6), "second frame should replace the first");
    expect(slot.retained() == 6, "only the latest frame is retained");
    expect(slot.latest(out, sequence, width, height, stride), "second frame should be readable");
    expect(sequence == 2 && width == 3 && height == 2 && out.size() == 6 && out[0] == 9, "second frame fields");

    const uint8_t wide[] = {1, 2};
    expect(!slot.publish(0, 1, 1, wide, 1), "zero width rejected");
    expect(!slot.publish(2, 1, 1, wide, 2), "stride shorter than width rejected");
    expect(!slot.publish(2, 2, 2, first, 3), "payload length must match stride times height");
    uint8_t tooBig[17] = {};
    expect(!slot.publish(17, 1, 17, tooBig, 17), "payload above capacity rejected");
    expect(slot.retained() == 6 && slot.latest(out, sequence, width, height, stride) && sequence == 2, "rejected publish keeps the latest frame");
    return 0;
}
