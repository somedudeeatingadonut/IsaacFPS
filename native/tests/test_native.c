/* Host-side unit tests for the platform-independent core of the native
 * layer (sigscan, adaptive controller, config parser). Built and run on
 * Linux during development; the Windows-only glue is separate.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../src/sigscan.h"
#include "../src/adaptive.h"
#include "../src/budget.h"
#include "../src/config.h"

static int g_pass = 0, g_fail = 0;

#define CHECK(name, cond)                                          \
    do {                                                           \
        if (cond) {                                                \
            g_pass++;                                              \
            printf("  ok  %s\n", name);                            \
        } else {                                                   \
            g_fail++;                                              \
            printf(" FAIL %s (line %d)\n", name, __LINE__);        \
        }                                                          \
    } while (0)

/* ------------------------------ sigscan ---------------------------------- */

static void test_sigscan(void)
{
    uint8_t buf[64];
    memset(buf, 0x90, sizeof(buf));
    /* plant a pattern at offset 17 */
    const uint8_t planted[] = { 0x55, 0x8b, 0xec, 0x83, 0xe4, 0xc0 };
    memcpy(buf + 17, planted, sizeof(planted));

    printf("== sigscan ==\n");
    CHECK("exact match found",
          ifps_sigscan(buf, sizeof(buf), "558bec83e4c0") == 17);
    CHECK("wildcard match found",
          ifps_sigscan(buf, sizeof(buf), "558b??83??c0") == 17);
    CHECK("all-wildcard matches at 0",
          ifps_sigscan(buf, sizeof(buf), "????") == 0);
    CHECK("no match returns -1",
          ifps_sigscan(buf, sizeof(buf), "deadbeef") == -1);
    CHECK("pattern longer than buffer rejected",
          ifps_sigscan(buf, 4, "558bec83e4c0") == -1);
    CHECK("malformed pattern rejected",
          ifps_sigscan(buf, sizeof(buf), "5g") == -1);
    CHECK("odd-length pattern rejected",
          ifps_sigscan(buf, sizeof(buf), "558") == -1);

    /* the real Entity::RenderShadowLayer signature, format-wise */
    CHECK("real signature format parses",
          ifps_sigscan(buf, sizeof(buf),
                       "558bec83e4c081ecb4000000f30f1005") == -1);
}

/* ------------------------------ adaptive --------------------------------- */

static void test_adaptive(void)
{
    IfpsAdaptive a;
    int i;

    printf("== adaptive controller ==\n");
    /* target 55 fps (18.2 ms), recover 70 fps (14.3 ms),
       30 frames to enter, 60 frames to exit */
    ifps_adaptive_init(&a, 55.0f, 70.0f, 30, 60, 1.0f);
    CHECK("starts with shadows on", a.shadows_off == 0);

    /* 25 ms frames (40 fps): should shed after ~30 frames */
    for (i = 0; i < 29; i++) ifps_adaptive_frame(&a, 25.0f);
    CHECK("does not flicker before threshold", a.shadows_off == 0);
    ifps_adaptive_frame(&a, 25.0f);
    CHECK("sheds shadows under sustained lag", a.shadows_off == 1);

    /* one good frame must not restore immediately (hysteresis) */
    ifps_adaptive_frame(&a, 10.0f);
    CHECK("single good frame does not restore", a.shadows_off == 1);

    /* 30 headroom frames: the EMA is below the recover threshold quickly,
       but the exit counter needs 60 sustained frames */
    for (i = 0; i < 30; i++) ifps_adaptive_frame(&a, 12.0f);
    CHECK("still shedding before exit counter completes", a.shadows_off == 1);
    for (i = 0; i < 80; i++) ifps_adaptive_frame(&a, 12.0f);
    CHECK("restores after sustained headroom", a.shadows_off == 0);

    /* in-between frame time (16 ms = 62.5 fps): between target and recover
       thresholds, so whichever state we're in, we stay there */
    ifps_adaptive_init(&a, 55.0f, 70.0f, 5, 5, 1.0f);
    for (i = 0; i < 100; i++) ifps_adaptive_frame(&a, 16.0f);
    CHECK("no oscillation in hysteresis band (from below)",
          a.shadows_off == 0);
    a.shadows_off = 1;
    a.exit_count = 0;
    for (i = 0; i < 100; i++) ifps_adaptive_frame(&a, 16.0f);
    CHECK("no oscillation in hysteresis band (from above)",
          a.shadows_off == 1);

    /* implausible samples ignored */
    ifps_adaptive_init(&a, 55.0f, 70.0f, 1, 1, 1.0f);
    ifps_adaptive_frame(&a, 0.0f);
    ifps_adaptive_frame(&a, -5.0f);
    ifps_adaptive_frame(&a, 99999.0f);
    CHECK("implausible samples ignored", a.frames_seen == 0);

    /* EMA tracks quickly */
    ifps_adaptive_init(&a, 55.0f, 70.0f, 30, 60, 1.0f);
    for (i = 0; i < 60; i++) ifps_adaptive_frame(&a, 25.0f);
    CHECK("ema converges to sample", a.ema_ms > 24.0f && a.ema_ms < 26.0f);

    /* tick_scale=0.5: 30Hz logic-tick source (Level::Update) normalized to
       60fps frame equivalents */
    ifps_adaptive_init(&a, 55.0f, 70.0f, 5, 5, 0.5f);
    for (i = 0; i < 30; i++) ifps_adaptive_frame(&a, 33.4f); /* healthy 30Hz */
    CHECK("healthy 30Hz ticks read as ~60fps (no shed)", a.shadows_off == 0 &&
          a.ema_ms > 16.0f && a.ema_ms < 17.5f);
    for (i = 0; i < 30; i++) ifps_adaptive_frame(&a, 50.0f); /* lagging ticks */
    CHECK("lagging 30Hz ticks trigger shed", a.shadows_off == 1);
}

/* ------------------------------- budget ---------------------------------- */

static void test_budget(void)
{
    IfpsBudget b;
    int i;

    printf("== budget accounting ==\n");
    ifps_budget_init(&b);
    CHECK("empty share is -1", ifps_budget_update_share(&b) < 0);

    /* render-bound profile: 25ms frames, only 5ms inside the measured call */
    for (i = 0; i < 60; i++) ifps_budget_sample(&b, 25.0f, 5.0f);
    CHECK("frame ema converges", b.frame_ema_ms > 24.0f && b.frame_ema_ms < 26.0f);
    CHECK("inside ema converges", b.update_ema_ms > 4.0f && b.update_ema_ms < 6.0f);
    {
        float share = ifps_budget_update_share(&b);
        CHECK("render-bound share ~20%", share > 0.15f && share < 0.25f);
    }

    /* logic-bound profile: 25ms frames, 18ms inside */
    ifps_budget_init(&b);
    for (i = 0; i < 60; i++) ifps_budget_sample(&b, 25.0f, 18.0f);
    {
        float share = ifps_budget_update_share(&b);
        CHECK("logic-bound share ~72%", share > 0.65f && share < 0.80f);
    }

    CHECK("implausible samples ignored",
          (ifps_budget_init(&b), ifps_budget_sample(&b, 0.0f, 5.0f),
           ifps_budget_sample(&b, 99999.0f, 5.0f), b.samples == 2 &&
           b.frame_ema_ms < 0.0f));

    printf("== force-test window ==\n");
    CHECK("disabled when seconds=0", ifps_force_active(5000, 1000, 0) == 0);
    CHECK("active inside window", ifps_force_active(5000, 1000, 10) == 1);
    CHECK("inactive after window", ifps_force_active(11001, 1000, 10) == 0);
    CHECK("boundary exact end", ifps_force_active(11000, 1000, 10) == 0);
    CHECK("clock before attach safe", ifps_force_active(500, 1000, 10) == 0);
}

/* ------------------------------- config ---------------------------------- */

static void test_config(void)
{
    IfpsConfig cfg;
    const char *tmp = "/tmp/ifps_test_config.ini";
    FILE *f;

    printf("== config ==\n");
    ifps_config_defaults(&cfg);
    CHECK("defaults sane", cfg.enabled == 1 &&
                               cfg.shadows_mode == IFPS_SHADOWS_ADAPTIVE &&
                               cfg.target_fps == 55.0f && cfg.log == 1);

    CHECK("parse enabled=0", ifps_config_parse_line(&cfg, "enabled=0") &&
                                 cfg.enabled == 0);
    CHECK("parse shadows=always", ifps_config_parse_line(&cfg, "shadows=always") &&
                                      cfg.shadows_mode == IFPS_SHADOWS_ALWAYS);
    CHECK("parse shadows=never", ifps_config_parse_line(&cfg, " shadows = never ") &&
                                     cfg.shadows_mode == IFPS_SHADOWS_NEVER);
    CHECK("parse shadows=1 as always", ifps_config_parse_line(&cfg, "shadows=1") &&
                                           cfg.shadows_mode == IFPS_SHADOWS_ALWAYS);
    CHECK("parse shadows=0 as never", ifps_config_parse_line(&cfg, "shadows=0") &&
                                          cfg.shadows_mode == IFPS_SHADOWS_NEVER);
    CHECK("parse target_fps", ifps_config_parse_line(&cfg, "target_fps=45") &&
                                  cfg.target_fps == 45.0f);
    CHECK("reject absurd target_fps", ifps_config_parse_line(&cfg, "target_fps=9999") &&
                                          cfg.target_fps == 45.0f);
    CHECK("comments skipped", ifps_config_parse_line(&cfg, "# comment") == 0);
    CHECK("sections skipped", ifps_config_parse_line(&cfg, "[Options]") == 0);
    CHECK("unknown keys reported", ifps_config_parse_line(&cfg, "bogus=1") == 0);
    CHECK("adaptive_fallback=always",
          ifps_config_parse_line(&cfg, "adaptive_fallback=always") &&
              cfg.adaptive_fallback == IFPS_SHADOWS_ALWAYS);
    CHECK("ground_impacts default on", cfg.ground_impacts == 1);
    CHECK("ground_impacts=0", ifps_config_parse_line(&cfg, "ground_impacts=0") &&
                                  cfg.ground_impacts == 0);
    CHECK("ground_impacts=1", ifps_config_parse_line(&cfg, "ground_impacts=1") &&
                                  cfg.ground_impacts == 1);
    CHECK("force_test default off", cfg.force_test == 0);
    CHECK("force_test=10", ifps_config_parse_line(&cfg, "force_test=10") &&
                               cfg.force_test == 10);
    CHECK("force_test rejects negative",
          ifps_config_parse_line(&cfg, "force_test=-5") && cfg.force_test == 10);
    CHECK("status_interval default", cfg.status_interval == 5.0f);
    CHECK("status_interval=2", ifps_config_parse_line(&cfg, "status_interval=2") &&
                                   cfg.status_interval == 2.0f);

    f = fopen(tmp, "w");
    fprintf(f, "# IsaacFPS native test config\nshadows=always\n"
               "target_fps = 50\nunknown_key=7\n");
    fclose(f);
    ifps_config_defaults(&cfg);
    CHECK("file loads", ifps_config_load_file(&cfg, tmp) == 0);
    CHECK("file values applied", cfg.shadows_mode == IFPS_SHADOWS_ALWAYS &&
                                     cfg.target_fps == 50.0f);
    ifps_config_defaults(&cfg);
    CHECK("missing file keeps defaults",
          ifps_config_load_file(&cfg, "/tmp/ifps_nonexistent.ini") != 0 &&
              cfg.enabled == 1);
    remove(tmp);
}

int main(void)
{
    test_sigscan();
    test_adaptive();
    test_budget();
    test_config();
    printf("\n%d passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
