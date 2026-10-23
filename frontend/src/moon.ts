/**
 * FORK d14tk: where the moon stands (azimuth from north, elevation), after the low-precision formulas of
 * SunCalc (V. Agafonkin, BSD, from Astronomy Answers); about a degree off, plenty for a disc in the sky.
 */
const RAD = Math.PI / 180;
const OBLIQUITY = RAD * 23.4397;

export interface MoonPosition {
  /** Degrees from north, clockwise (like sun.sun). */
  azimuth: number;
  /** Degrees above the horizon, refraction included. */
  elevation: number;
}

export function moonPosition(date: Date, lat: number, lon: number): MoonPosition {
  const d = date.getTime() / 86400000 - 0.5 + 2440588 - 2451545;
  const L = RAD * (218.316 + 13.176396 * d);
  const M = RAD * (134.963 + 13.064993 * d);
  const F = RAD * (93.272 + 13.22935 * d);
  const l = L + RAD * 6.289 * Math.sin(M);
  const b = RAD * 5.128 * Math.sin(F);
  const ra = Math.atan2(Math.sin(l) * Math.cos(OBLIQUITY) - Math.tan(b) * Math.sin(OBLIQUITY), Math.cos(l));
  const dec = Math.asin(Math.sin(b) * Math.cos(OBLIQUITY) + Math.cos(b) * Math.sin(OBLIQUITY) * Math.sin(l));
  const phi = RAD * lat;
  const H = RAD * (280.16 + 360.9856235 * d) + RAD * lon - ra;
  let h = Math.asin(Math.sin(phi) * Math.sin(dec) + Math.cos(phi) * Math.cos(dec) * Math.cos(H));
  const az = Math.atan2(Math.sin(H), Math.cos(H) * Math.sin(phi) - Math.tan(dec) * Math.cos(phi));
  const hr = Math.max(h, 0);
  h += 0.0002967 / Math.tan(hr + 0.00312536 / (hr + 0.08901179));
  return { azimuth: (((az / RAD + 180) % 360) + 360) % 360, elevation: h / RAD };
}
