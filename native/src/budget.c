#include "budget.h"

void ifps_budget_init(IfpsBudget *b)
{
    b->frame_ema_ms = -1.0f;
    b->update_ema_ms = -1.0f;
    b->samples = 0;
}

static float ema(float prev, float sample)
{
    if (prev < 0.0f) return sample;
    return prev * 0.9f + sample * 0.1f;
}

void ifps_budget_sample(IfpsBudget *b, float frame_ms, float update_ms)
{
    if (frame_ms > 0.0f && frame_ms < 5000.0f)
        b->frame_ema_ms = ema(b->frame_ema_ms, frame_ms);
    if (update_ms >= 0.0f && update_ms < 5000.0f)
        b->update_ema_ms = ema(b->update_ema_ms, update_ms);
    b->samples++;
}

float ifps_budget_update_share(const IfpsBudget *b)
{
    if (b->frame_ema_ms <= 0.0f || b->update_ema_ms < 0.0f) return -1.0f;
    {
        float share = b->update_ema_ms / b->frame_ema_ms;
        if (share > 1.0f) share = 1.0f;
        return share;
    }
}

int ifps_force_active(long long now_ms, long long attach_ms,
                      int force_seconds)
{
    if (force_seconds <= 0) return 0;
    if (now_ms < attach_ms) return 0;
    return (now_ms - attach_ms) < (long long)force_seconds * 1000LL;
}
