#include "config.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void ifps_config_defaults(IfpsConfig *cfg)
{
    cfg->enabled = 1;
    cfg->shadows_mode = IFPS_SHADOWS_ADAPTIVE;
    cfg->adaptive_fallback = IFPS_SHADOWS_NEVER;
    cfg->target_fps = 55.0f;
    cfg->recover_fps = 70.0f;
    cfg->log = 1;
}

static void lower_inplace(char *s)
{
    for (; *s; s++) *s = (char)tolower((unsigned char)*s);
}

static int parse_bool(const char *v, int fallback)
{
    if (!v || !*v) return fallback;
    if (!strcmp(v, "1") || !strcmp(v, "true") || !strcmp(v, "on") ||
        !strcmp(v, "yes"))
        return 1;
    if (!strcmp(v, "0") || !strcmp(v, "false") || !strcmp(v, "off") ||
        !strcmp(v, "no"))
        return 0;
    return fallback;
}

int ifps_config_parse_line(IfpsConfig *cfg, const char *line)
{
    char key[64];
    char val[64];
    const char *eq;
    size_t kl, vl, i;

    if (!line) return 0;
    while (*line == ' ' || *line == '\t') line++;
    if (*line == '#' || *line == ';' || *line == '\0' || *line == '\r' ||
        *line == '\n' || *line == '[')
        return 0;

    eq = strchr(line, '=');
    if (!eq) return 0;

    kl = (size_t)(eq - line);
    if (kl >= sizeof(key)) return 0;
    for (i = 0; i < kl; i++) key[i] = line[i];
    key[kl] = '\0';
    while (kl > 0 && (key[kl - 1] == ' ' || key[kl - 1] == '\t'))
        key[--kl] = '\0';
    lower_inplace(key);

    eq++;
    while (*eq == ' ' || *eq == '\t') eq++;
    vl = 0;
    while (eq[vl] && eq[vl] != '\r' && eq[vl] != '\n' && eq[vl] != '#' &&
           eq[vl] != ';' && vl < sizeof(val) - 1) {
        val[vl] = eq[vl];
        vl++;
    }
    while (vl > 0 && (val[vl - 1] == ' ' || val[vl - 1] == '\t')) vl--;
    val[vl] = '\0';
    lower_inplace(val);

    if (!strcmp(key, "enabled")) {
        cfg->enabled = parse_bool(val, cfg->enabled);
    } else if (!strcmp(key, "log")) {
        cfg->log = parse_bool(val, cfg->log);
    } else if (!strcmp(key, "shadows")) {
        if (!strcmp(val, "adaptive")) cfg->shadows_mode = IFPS_SHADOWS_ADAPTIVE;
        else if (!strcmp(val, "always")) cfg->shadows_mode = IFPS_SHADOWS_ALWAYS;
        else if (!strcmp(val, "never")) cfg->shadows_mode = IFPS_SHADOWS_NEVER;
        else cfg->shadows_mode = parse_bool(val, IFPS_SHADOWS_ADAPTIVE)
                                     ? IFPS_SHADOWS_ALWAYS
                                     : IFPS_SHADOWS_NEVER;
    } else if (!strcmp(key, "adaptive_fallback")) {
        if (!strcmp(val, "always"))
            cfg->adaptive_fallback = IFPS_SHADOWS_ALWAYS;
        else if (!strcmp(val, "never"))
            cfg->adaptive_fallback = IFPS_SHADOWS_NEVER;
        else
            cfg->adaptive_fallback = parse_bool(val, 0)
                                         ? IFPS_SHADOWS_ALWAYS
                                         : IFPS_SHADOWS_NEVER;
    } else if (!strcmp(key, "target_fps")) {
        float f = (float)atof(val);
        if (f >= 10.0f && f <= 240.0f) cfg->target_fps = f;
    } else if (!strcmp(key, "recover_fps")) {
        float f = (float)atof(val);
        if (f >= 10.0f && f <= 240.0f) cfg->recover_fps = f;
    } else {
        return 0;
    }
    return 1;
}

int ifps_config_load_file(IfpsConfig *cfg, const char *path)
{
    FILE *f;
    char line[256];

    f = fopen(path, "r");
    if (!f) return -1;
    while (fgets(line, sizeof(line), f)) {
        ifps_config_parse_line(cfg, line);
    }
    fclose(f);
    return 0;
}
