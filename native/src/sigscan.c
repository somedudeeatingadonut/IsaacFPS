#include "sigscan.h"
#include <string.h>

static int hexval(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

int ifps_pattern_parse(const char *pattern, uint8_t *bytes, uint8_t *mask,
                       int max_len)
{
    int n = 0;
    const char *p = pattern;

    if (!pattern) return -1;
    while (*p) {
        while (*p == ' ' || *p == '\t') p++;
        if (!*p) break;
        if (n >= max_len) return -1;

        if (p[0] == '?' && p[1] == '?') {
            bytes[n] = 0;
            mask[n] = 0;
            p += 2;
        } else {
            int hi = hexval(p[0]);
            int lo = p[1] ? hexval(p[1]) : -1;
            if (hi < 0 || lo < 0) return -1;
            bytes[n] = (uint8_t)((hi << 4) | lo);
            mask[n] = 1;
            p += 2;
        }
        n++;
    }
    return n;
}

long ifps_sigscan(const uint8_t *base, size_t len, const char *pattern)
{
    uint8_t bytes[256];
    uint8_t mask[256];
    int n = ifps_pattern_parse(pattern, bytes, mask, (int)sizeof(bytes));
    size_t i, end;

    if (n <= 0 || (size_t)n > len || !base) return -1;
    end = len - (size_t)n;
    for (i = 0; i <= end; i++) {
        int j, ok = 1;
        for (j = 0; j < n; j++) {
            if (mask[j] && base[i + j] != bytes[j]) {
                ok = 0;
                break;
            }
        }
        if (ok) return (long)i;
    }
    return -1;
}
