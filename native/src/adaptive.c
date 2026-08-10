#include "adaptive.h"

void ifps_adaptive_init(IfpsAdaptive *a, float target_fps, float recover_fps,
                        int enter_frames, int exit_frames, float tick_scale)
{
    if (target_fps < 10.0f) target_fps = 10.0f;
    if (recover_fps < target_fps) recover_fps = target_fps + 10.0f;
    if (tick_scale <= 0.0f) tick_scale = 1.0f;

    a->target_ms = 1000.0f / target_fps;
    a->recover_ms = 1000.0f / recover_fps;
    a->tick_scale = tick_scale;
    a->enter_frames = enter_frames > 0 ? enter_frames : 30;
    a->exit_frames = exit_frames > 0 ? exit_frames : 120;
    a->ema_ms = -1.0f;
    a->enter_count = 0;
    a->exit_count = 0;
    a->shadows_off = 0;
    a->frames_seen = 0;
}

void ifps_adaptive_frame(IfpsAdaptive *a, float sample_ms)
{
    float frame_ms = sample_ms * a->tick_scale;

    if (frame_ms <= 0.0f || frame_ms > 5000.0f) return;

    a->frames_seen++;
    if (a->ema_ms < 0.0f) {
        a->ema_ms = frame_ms;
    } else {
        a->ema_ms = a->ema_ms * 0.9f + frame_ms * 0.1f;
    }

    if (!a->shadows_off) {
        if (a->ema_ms > a->target_ms) {
            if (++a->enter_count >= a->enter_frames) {
                a->shadows_off = 1;
                a->enter_count = 0;
                a->exit_count = 0;
            }
        } else {
            a->enter_count = 0;
        }
    } else {
        if (a->ema_ms < a->recover_ms) {
            if (++a->exit_count >= a->exit_frames) {
                a->shadows_off = 0;
                a->enter_count = 0;
                a->exit_count = 0;
            }
        } else {
            a->exit_count = 0;
        }
    }
}
