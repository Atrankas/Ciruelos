// SPDX-FileCopyrightText: Copyright 2024 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

#include <condition_variable>
#include <span>

#include "core/libraries/videoout/buffer.h"
#include "imgui/imgui_texture.h"
#include "video_core/renderer_vulkan/host_passes/fsr_pass.h"
#include "video_core/renderer_vulkan/host_passes/pp_pass.h"
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_scheduler.h"
#include "video_core/renderer_vulkan/vk_swapchain.h"
#include "video_core/renderer_vulkan/vk_vr_exporter.h"
#include "video_core/texture_cache/texture_cache.h"

namespace Frontend {
class WindowSDL;
}

namespace AmdGpu {
struct Liverpool;
}

namespace Vulkan {

struct Frame {
    u32 width;
    u32 height;
    VmaAllocation allocation;
    vk::Image image;
    vk::ImageView image_view;
    vk::Fence present_done;
    /// The timeline the frame's commands were submitted on, and its tick once they have run.
    MasterSemaphore* ready_timeline{};
    vk::Semaphore ready_semaphore;
    u64 ready_tick;
    bool is_hdr{false};
    u8 id{};
    /// The VR host buffer this frame lives in, or -1 for a frame that is shown on the window.
    s8 host_buffer{-1};
    /// Whether this frame exists only for the VR host, the title's one picture having gone into
    /// the host's buffer and nothing having been drawn for the window at all (see
    /// Presenter::PresentHostFrame). It is then never presented, and its slot in the pool is
    /// only held until the guest's flip has been completed.
    bool host_only{false};

    ImTextureID imgui_texture;
};

/// What a frame of the emulated headset is drawn into: the frame that goes on the window (or to
/// the application that owns the headset, on a machine where that is another process), and,
/// where the machine has a headset of its own, the frame that goes there.
struct HmdFrames {
    Frame* shown{};
    Frame* exported{};

    explicit operator bool() const {
        return shown != nullptr || exported != nullptr;
    }
};

enum SchedulerType {
    Draw,
    Present,
    CpuFlip,
};

/// What to do with the picture of a title that never draws for the emulated headset: one made for
/// a television, which would otherwise have nowhere to be seen at all (the emulator runs without a
/// window when an application drives a headset of its own).
enum class FlatPictures {
    /// Show it while the title has not drawn for the headset yet, and stop the moment it does:
    /// a title that boots on the television and then takes the headset over is shown both ways.
    UntilHeadset,
    /// Never show it (SHADPS4_VR_FLAT=0): the title is left as it was, with nothing on screen.
    Never,
    /// Show it even where the title draws for the headset (SHADPS4_VR_FLAT=1), to see any title
    /// on a flat screen.
    Always,
};

class Rasterizer;

class Presenter {
public:
    Presenter(Frontend::WindowSDL& window, AmdGpu::Liverpool* liverpool);
    ~Presenter();

    HostPasses::PostProcessingPass::Settings& GetPPSettingsRef() {
        return pp_settings;
    }

    HostPasses::FsrPass::Settings& GetFsrSettingsRef() {
        return fsr_settings;
    }

    Frontend::WindowSDL& GetWindow() const {
        return window;
    }

    Rasterizer& GetRasterizer() const {
        return *rasterizer.get();
    }

    bool IsHDRSupported() const {
        return swapchain.HasHDR();
    }

    void SetHDR(bool enable) {
        if (!IsHDRSupported()) {
            return;
        }
        swapchain.SetHDR(enable);
        pp_settings.hdr = enable ? 1 : 0;
    }

    VideoCore::Image& RegisterVideoOutSurface(
        const Libraries::VideoOut::BufferAttributeGroup& attribute, VAddr cpu_address) {
        vo_buffers_addr.emplace_back(cpu_address);
        auto desc = VideoCore::TextureCache::ImageDesc{attribute, cpu_address};
        const auto image_id = texture_cache.FindImage(desc);
        auto& image = texture_cache.GetImage(image_id);
        image.usage.vo_surface = 1u;
        return image;
    }

    bool IsVideoOutSurface(const AmdGpu::ColorBuffer& color_buffer) const;

    Frame* PrepareFrame(const Libraries::VideoOut::BufferAttributeGroup& attribute,
                        VAddr cpu_address);

    /// Composes the two eye images of a headset frame side by side into a presentation frame
    /// and stamps it with `frame_id` so the host can match it to a head pose.
    HmdFrames PrepareHmdFrame(std::span<const AmdGpu::Image, 2> eye_textures,
                              const Core::Vr::Fov& fov, u32 frame_id,
                              u32& eye_width, u32& eye_height);

    /// Hands a frame made by PrepareHmdFrame to the VR host. Returns false for a frame that is
    /// not one of the host's, which has to be presented as usual.
    bool DeliverHmdFrame(Frame* frame, const Core::Vr::PresentedFrame& info);

    /// Whether this title's picture is going to the VR host on a screen of its own, and the host
    /// is ready for it: the frame now being prepared needs nothing drawn for the window, only
    /// the title's own picture for the host. See PrepareFrame and PresentHostFrame.
    bool WantsFlatFrames();

    /// Hands over the flat picture drawn for the frame before this one, if the GPU is done with
    /// it, and lets go of it if it is not. Called at the end of a frame that goes to the host
    /// instead of the window: the picture is handed over by the thread that draws, one frame
    /// after it was drawn, and never waits for the GPU (see Presenter::PrepareFlatFrame).
    void TakeFlatFrame();

    /// Whether `frame` is one that went to the host rather than to the window.
    bool IsHostFrame(const Frame* frame) const {
        return frame != nullptr && frame->host_only;
    }

    /// Completes the guest's flip for a frame that went to the host instead of the window: there
    /// is nothing to show on a window, and nothing to wait for, so the frame goes straight back
    /// to the pool and the title is told at once that it may go on. Called in place of Present.
    void PresentHostFrame(Frame* frame);

    /// Whether the GPU has finished drawing `frame`.
    bool IsFrameFinished(const Frame* frame);
    /// Whether the GPU still has drawing of the title's before it.
    bool IsGpuBusy();

    Frame* PrepareBlankFrame(bool present_thread);

    void Present(Frame* frame, bool is_reusing_frame = false);
    Frame* PrepareLastFrame();

private:
    Frame* GetRenderFrame();

    /// Draws the picture of a title that does not draw for the headset into one of the VR host's
    /// buffers, to be shown there on a screen of its own: `picture` is the title's finished
    /// output, `size` its size, and `picture_rect` is filled in with the part of the host's
    /// buffer that holds it. Returns the frame that lives in the host's buffer, or null when
    /// there is no host to draw for.
    Frame* PrepareFlatFrame(vk::ImageView picture, vk::Extent2D size, vk::CommandBuffer cmdbuf,
                            FlatPicture& picture_rect);

    /// Returns a frame to the pool of frames that can be drawn into, without presenting it.
    void ReleaseFrame(Frame* frame);

    /// Writes a thumbnail of every image the guest GPU rendered into to <UserDir>/rt_dump.
    void DumpGpuImages();

    void RecreateFrame(Frame* frame, u32 width, u32 height);

    void SetExpectedGameSize(s32 width, s32 height);

private:
    std::optional<float> expected_ratio{1920.0 / 1080.0f};
    u32 expected_frame_width{1920};
    u32 expected_frame_height{1080};

    Frontend::WindowSDL& window;
    Instance instance;
    HostPasses::FsrPass fsr_pass;
    HostPasses::FsrPass::Settings fsr_settings{};
    HostPasses::PostProcessingPass::Settings pp_settings{};
    HostPasses::PostProcessingPass pp_pass;
    /// The same pass for the frames of the machine's own headset, which have a format of their
    /// own. Only made where there is such a headset to draw for.
    HostPasses::PostProcessingPass hmd_pp_pass;
    AmdGpu::Liverpool* liverpool;
    Scheduler draw_scheduler;
    Scheduler present_scheduler;
    Scheduler flip_scheduler;
    Swapchain swapchain;
    std::unique_ptr<Rasterizer> rasterizer;
    std::unique_ptr<VrExporter> vr_exporter;
    VideoCore::TextureCache& texture_cache;
    vk::UniqueCommandPool command_pool;
    std::vector<Frame> present_frames;
    std::queue<Frame*> free_queue;
    Frame* last_submit_frame{};
    std::mutex free_mutex;
    std::condition_variable free_cv;
    std::condition_variable_any frame_cv;
    std::optional<ImGui::RefCountedTexture> splash_img;
    std::vector<VAddr> vo_buffers_addr;
    /// How the picture of a title that does not draw for the headset is treated.
    FlatPictures flat_pictures{FlatPictures::UntilHeadset};
    /// Whether this title has drawn a frame for the emulated headset at all: once it has, its
    /// pictures are the eyes'.
    bool seen_headset_frame{false};
    /// The flat picture drawn for the frame before the one being prepared, waiting to be handed
    /// to the host, and where in its buffer it sits. It lives in that buffer and is not one of
    /// the pool's frames, so the next slot Acquire takes is another one: holding it here while
    /// the next frame is drawn is what keeps the handover off the thread that presents.
    Frame* pending_flat{};
    FlatPicture pending_flat_picture{};
    /// Whether the one line that says a flat picture is on its way to the host has been written.
    bool flat_announced{false};
};

} // namespace Vulkan
