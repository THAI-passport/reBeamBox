/* nn20 framing for the 0x01F0 service. Pure functions, no DOM, no dependencies. Mirrors rebeambox/nn20.py. */
(function (root) {
  "use strict";
  var MAX_DATA = 446;

  function checksum(bytes) {
    var s = 0;
    for (var i = 0; i < bytes.length; i++) s = (s + bytes[i]) & 0xff;
    return (256 - s) & 0xff;
  }

  /* data bytes per packet for an ATT MTU: P = min(446, mtu - 12), ATT minimum 23 */
  function dataPerPacket(mtu) {
    return Math.min(MAX_DATA, Math.max(23, mtu) - 12);
  }

  function u32(view, off, v) { view.setUint32(off, v >>> 0, true); }

  /* 0x12345678 animation container; one JPEG gives the one-frame "type 5 still". */
  function gifContainer(jpegs, intervalMs, width, height) {
    var n = jpegs.length, headLen = n * 16 + 32, total = headLen, i;
    var offs = [];
    for (i = 0; i < n; i++) { offs.push(total); total += 32 + jpegs[i].length; }
    var out = new Uint8Array(total), v = new DataView(out.buffer);
    u32(v, 0, 0x12345678); u32(v, 4, n * 16 + 24); u32(v, 8, n); u32(v, 12, intervalMs);
    var label = "output/" + intervalMs + "ms";
    for (i = 0; i < 12 && i < label.length; i++) out[16 + i] = label.charCodeAt(i);
    for (i = 0; i < n; i++) {
      var name = "frame_" + ("00000" + (i + 1)).slice(-5) + ".";
      for (var k = 0; k < 12; k++) out[32 + i * 16 + k] = name.charCodeAt(k);
      u32(v, 32 + i * 16 + 12, offs[i]);
    }
    for (i = 0; i < n; i++) {
      var p = offs[i], nxt = i < n - 1 ? offs[i + 1] : offs[0];
      u32(v, p, offs[i]); u32(v, p + 4, nxt);
      out[p + 8] = 11; out[p + 9] = 0;
      v.setInt16(p + 10, 0, true); v.setInt16(p + 12, width, true); v.setInt16(p + 14, height, true);
      v.setInt32(p + 16, offs[i] + 32, true); v.setInt32(p + 20, jpegs[i].length, true);
      v.setInt32(p + 24, 0, true); v.setInt32(p + 28, 0, true);
      out.set(jpegs[i], p + 32);
    }
    u32(v, 28, total - 1);
    return out;
  }

  /* envelope {"type":T,"data":<payload>} split into frames */
  function buildFrames(type, payload, mtu) {
    var head = new TextEncoder().encode('{"type":' + type + ',"data":');
    var env = new Uint8Array(head.length + payload.length + 1);
    env.set(head, 0); env.set(payload, head.length); env[env.length - 1] = 0x7d;
    var P = dataPerPacket(mtu), n = Math.ceil(env.length / P), frames = [];
    if (n > 65535) throw new Error("payload too large");
    for (var i = 0; i < n; i++) {
      var chunk = env.subarray(i * P, Math.min(env.length, (i + 1) * P));
      var f = new Uint8Array(chunk.length + 9), v = new DataView(f.buffer);
      f[0] = 0xf1; f[1] = type;
      v.setUint16(2, n, false); v.setUint16(4, n - 1 - i, false); v.setUint16(6, chunk.length, false);
      f.set(chunk, 8);
      f[f.length - 1] = checksum(f.subarray(0, f.length - 1));
      frames.push(f);
    }
    return frames;
  }

  /* parse badge replies on 0x01F2: A0 type u16 u8(len) json checksum */
  function parseReplies(buf) {
    var out = [], b = buf;
    for (;;) {
      var i = b.indexOf(0xa0);
      if (i < 0) return { msgs: out, rest: new Uint8Array(0) };
      b = b.subarray(i);
      if (b.length < 6) return { msgs: out, rest: b };
      var L = b[4];
      if (b.length < L + 6) return { msgs: out, rest: b };
      if (checksum(b.subarray(0, 5 + L)) !== b[5 + L]) { b = b.subarray(1); continue; }
      out.push({ type: b[1], text: new TextDecoder().decode(b.subarray(5, 5 + L)) });
      b = b.subarray(L + 6);
    }
  }

  function toHex(bytes) {
    return Array.prototype.map.call(bytes, function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
  }

  var api = { MAX_DATA: MAX_DATA, checksum: checksum, dataPerPacket: dataPerPacket, gifContainer: gifContainer,
              buildFrames: buildFrames, parseReplies: parseReplies, toHex: toHex, TYPE_GIF: 5, TYPE_ALBUM: 6 };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.Nn20 = api;
})(typeof self !== "undefined" ? self : this);
