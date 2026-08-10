/* IsaacFPS native :: byte-pattern signature scanner.
 *
 * Same mechanism REPENTOGON's libzhl uses: functions in the game binary are
 * located by byte signatures (see the .zhl files under libzhl/functions in
 * the REPENTOGON repo). Patterns are hex byte pairs; "??" is a wildcard.
 *
 * This file is platform-independent and unit-tested on the host.
 */
#ifndef IFPS_SIGSCAN_H
#define IFPS_SIGSCAN_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Parse a signature pattern ("558bec83??c0") into bytes+mask arrays.
 * Returns the number of pattern bytes, or -1 on malformed input / overflow. */
int ifps_pattern_parse(const char *pattern, uint8_t *bytes, uint8_t *mask,
                       int max_len);

/* Scan [base, base+len) for the pattern. Returns the byte offset of the
 * first match, or -1 if not found. */
long ifps_sigscan(const uint8_t *base, size_t len, const char *pattern);

#ifdef __cplusplus
}
#endif

#endif /* IFPS_SIGSCAN_H */
