/* IsaacFPS native :: adaptive quality controller.
 *
 * A small state machine fed with one frame-time sample per rendered frame.
 * When the smoothed frame time stays above the target it decides that the
 * game is lagging (and expensive visuals can be shed); when there is
 * sustained headroom again it restores them. Separate enter/exit thresholds
 * and counters provide hysteresis so the decision cannot flicker.
 *
 * Platform-independent and unit-tested on the host.
 */
#ifndef IFPS_ADAPTIVE_H
#define IFPS_ADAPTIVE_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct IfpsAdaptive {
    float target_ms;    /* smoothed frame time above this = "lagging"    */
    float recover_ms;   /* smoothed frame time below this = "headroom"  */
    int enter_frames;   /* consecutive lagging frames before shedding   */
    int exit_frames;    /* consecutive headroom frames before restoring */

    float ema_ms;       /* exponential moving average of frame time     */
    int enter_count;
    int exit_count;
    int shadows_off;    /* current decision: 1 = shed expensive visuals */
    long frames_seen;
} IfpsAdaptive;

void ifps_adaptive_init(IfpsAdaptive *a, float target_fps, float recover_fps,
                        int enter_frames, int exit_frames);

/* Feed one frame-time sample (milliseconds). Ignores implausible values. */
void ifps_adaptive_frame(IfpsAdaptive *a, float frame_ms);

#ifdef __cplusplus
}
#endif

#endif /* IFPS_ADAPTIVE_H */
