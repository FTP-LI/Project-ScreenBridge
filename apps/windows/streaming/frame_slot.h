#pragma once

#include <cstdint>
#include <cstring>
#include <mutex>
#include <vector>

// One latest frame for the user process. A newer publish replaces the previous
// bytes; this is not a queue and it does not talk to the display driver yet.
class FrameSlot
{
public:
    explicit FrameSlot(uint32_t capacity)
        : capacity_(capacity), payload_(capacity)
    {
    }

    bool publish(uint32_t width, uint32_t height, uint32_t stride, const uint8_t* data, uint32_t size)
    {
        if (data == nullptr || width == 0 || height == 0 || stride < width)
        {
            return false;
        }
        if (height > UINT32_MAX / stride || size != stride * height || size > capacity_)
        {
            return false;
        }
        std::lock_guard<std::mutex> lock(mutex_);
        std::memcpy(payload_.data(), data, size);
        sequence_ += 1;
        width_ = width;
        height_ = height;
        stride_ = stride;
        size_ = size;
        checksum_ = checksum(data, size);
        return true;
    }

    bool latest(std::vector<uint8_t>& out, uint32_t& sequence, uint32_t& width, uint32_t& height, uint32_t& stride) const
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (sequence_ == 0)
        {
            return false;
        }
        out.assign(payload_.begin(), payload_.begin() + size_);
        if (checksum(out.data(), static_cast<uint32_t>(out.size())) != checksum_)
        {
            return false;
        }
        sequence = sequence_;
        width = width_;
        height = height_;
        stride = stride_;
        return true;
    }

    uint32_t retained() const
    {
        std::lock_guard<std::mutex> lock(mutex_);
        return size_;
    }

private:
    static uint32_t checksum(const uint8_t* data, uint32_t size)
    {
        uint32_t crc = 0xFFFFFFFFu;
        for (uint32_t i = 0; i < size; ++i)
        {
            crc ^= data[i];
            for (int bit = 0; bit < 8; ++bit)
            {
                uint32_t mask = 0u - (crc & 1u);
                crc = (crc >> 1) ^ (0xEDB88320u & mask);
            }
        }
        return crc ^ 0xFFFFFFFFu;
    }

    mutable std::mutex mutex_;
    uint32_t capacity_;
    std::vector<uint8_t> payload_;
    uint32_t sequence_ = 0;
    uint32_t width_ = 0;
    uint32_t height_ = 0;
    uint32_t stride_ = 0;
    uint32_t size_ = 0;
    uint32_t checksum_ = 0;
};
