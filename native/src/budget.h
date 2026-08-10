/* IsaacFPS native :: frame budget accounting + force-test window.
 * Platform-independent and unit-tested on the host.
 */
#ifndef IFPS_BUDGET_H
#define IFPS_BUDGET_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct IfpsBudget {
    float frame_ema_ms;  /* smoothed interval between measurement calls   */
    float update_ema_ms; /* smoothed time spent inside the measured call  */
    long samples;
} IfpsBudget;

void ifps_budget_init(IfpsBudget *b);

/* Feed one sample: frame_ms = time since previous measurement call,
 * update_ms = duration of the measured call itself. */
void ifps_budget_sample(IfpsBudget *b, float frame_ms, float update_ms);

/* Share of the frame spent inside the measured update call (0..1),
 * or -1 when there is no data yet. */
float ifps_budget_update_share(const IfpsBudget *b);

/* Force-test window: returns 1 while (now_ms - attach_ms) is within the
 * forced shed period. force_seconds <= 0 disables the feature. */
int ifps_force_active(long long now_ms, long long attach_ms,
                      int force_seconds);

#ifdef __cplusplus
}
#endif

#endif /* IFPS_BUDGET_H */
