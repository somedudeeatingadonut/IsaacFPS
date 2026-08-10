/* IsaacFPS native :: config file parsing (isaacfps_native.ini).
 * Platform-independent and unit-tested on the host.
 */
#ifndef IFPS_CONFIG_H
#define IFPS_CONFIG_H

#ifdef __cplusplus
extern "C" {
#endif

enum {
    IFPS_SHADOWS_ADAPTIVE = 0, /* shed shadows only while lagging (default) */
    IFPS_SHADOWS_ALWAYS = 1,   /* always skip entity shadows                 */
    IFPS_SHADOWS_NEVER = 2     /* hook installed but never skips            */
};

typedef struct IfpsConfig {
    int enabled;          /* master switch (default 1)             */
    int shadows_mode;     /* one of IFPS_SHADOWS_*                 */
    int ground_impacts;   /* skip DoGroundImpactEffects while shedding:
                             1 = adaptive (default), 0 = never hook  */
    int adaptive_fallback;/* mode used when frame measurement is
                             unavailable: IFPS_SHADOWS_ALWAYS or
                             _NEVER (default)                       */
    float target_fps;     /* lag threshold for adaptive (default 55) */
    float recover_fps;    /* headroom threshold (default 70)         */
    int force_test;       /* seconds of forced shedding at attach, as a
                             visual self-test of the hooks (default 0) */
    float status_interval;/* seconds between periodic status log lines
                             (default 5; 0 disables)                  */
    int log;              /* write isaacfps_native.log (default 1)   */
} IfpsConfig;

void ifps_config_defaults(IfpsConfig *cfg);

/* Parse one "key=value" line. Returns 1 if the key was recognized. */
int ifps_config_parse_line(IfpsConfig *cfg, const char *line);

/* Load a whole file (missing file = keep defaults). Returns 0 on success. */
int ifps_config_load_file(IfpsConfig *cfg, const char *path);

#ifdef __cplusplus
}
#endif

#endif /* IFPS_CONFIG_H */
