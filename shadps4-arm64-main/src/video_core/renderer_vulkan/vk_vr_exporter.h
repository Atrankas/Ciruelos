// SPDX-FileCopyrightText: Copyright 2026 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

#include <memory>
#include <vector>

#include "common/types.h"
#include "core/vr/vr_protocol.h"
#include "core/vr/vr_runtime.h"
#include "video_core/renderer_vulkan/vk_common.h"

namespace Core::Vr {
struct HostBuffers;
}

namespace Vulkan {

class Instance;
class Scheduler;
struct Frame;

/// Where in one of the host's buffers a flat picture sits, in pixels of that buffer: the part
/// the title is drawn in, the rest of the buffer being black.
struct FlatPicture {
    u32 x{};
    u32 y{};
    u32 width{};
    u32 height{};
};

/// Delivers the frames of the emulated headset to the application that drives the real one.
/// That application owns the images. Where the driver can attach to them the frames are rendered
/// straight into them, otherwise they are rendered here and their pixels copied over.
class VrExporter {
public:
    VrExporter(const Instance& instance, Scheduler& scheduler);
    ~VrExporter();

    /// Returns the frame the next headset image has to be rendered into, or null when there is
    /// no host to deliver it to (yet).
    Frame* Acquire(vk::Format format);

    /// The same for the headset of the machine the emulator runs on (Core::Vr::OpenXrHost): a
    /// frame of `width` by `height` in that host's format, or null while that headset shows
    /// nothing. Such a frame is drawn next to the one for the window, not in place of it.
    Frame* AcquireLocal(u32 width, u32 height);
    /// Whether frames can be had from AcquireLocal at times.
    bool HasLocalHost() const;

    /// Records whatever gets the rendered frame into the host's image. Call after its draws.
    void Finalize(Frame* frame, vk::CommandBuffer cmdbuf);

    /// Tells the host the frame is ready. Blocks until the GPU is done with it.
    void Deliver(Frame* frame, const Core::Vr::PresentedFrame& info);

    /// The same for a title that does not use the emulated headset: one ordinary picture, drawn
    /// into `picture`'s part of the buffer, for the host to put on a screen of its own.
    void DeliverFlat(Frame* frame, const FlatPicture& picture);

    /// Whether the host has offered the buffers frames are delivered in, and picked up already:
    /// until it has there is nothing to render a frame of a title that does not draw for the
    /// headset into, and the title belongs on the window. Unlike Acquire, which waits for the
    /// offer (Setup), this says what is known now, and is cheap enough to ask from any thread.
    bool CanDeliver() const {
        return !failed && !slots.empty();
    }

    /// Whether a title that never draws for the headset may be the one that sets the buffers up.
    /// Setup runs on the first Acquire, so CanDeliver alone would keep such a title off the host
    /// for ever (nothing else would ever call Acquire): the host is there, and nothing has gone
    /// wrong with it.
    bool MayDeliver() const;

private:
    struct Slot;

    bool Setup(vk::Format format);
    bool Import(Slot& slot, const Core::Vr::HostBuffers& offer, vk::Format format);
    bool CreateCopy(Slot& slot, const Core::Vr::HostBuffers& offer, vk::Format format);
    void Destroy(Slot& slot);

    /// Waits for the frame's commands to have run, puts its pixels in the host's mapping where
    /// the image could not be rendered in place, and sends `message` on with the slot's index.
    void HandOver(Frame* frame, Core::Vr::Protocol::Frame& message);

    bool IsLocal(const Frame* frame) const;

    const Instance& instance;
    Scheduler& scheduler;
    /// Frames standing for the images of the machine's own headset host, by its index.
    std::vector<std::unique_ptr<Frame>> local_frames;
    std::vector<std::unique_ptr<Slot>> slots;
    u32 next_slot{};
    u32 stride{};
    bool swap_red_blue{};
    bool failed{};
};

} // namespace Vulkan
