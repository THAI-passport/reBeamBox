/* Web Bluetooth harness for the nn20 path (service 0x01F0). Vanilla JS, no network calls, no analytics. */
(function () {
  "use strict";
  var SERVICE = 0x01f0, WRITE = 0x01f1, NOTIFY = 0x01f2;
  var $ = function (id) { return document.getElementById(id); };
  var state = { device: null, write: null, status: null, jpeg: null, rx: new Uint8Array(0), acks: [] };

  function log(msg) {
    var el = $("log");
    el.textContent += msg + "\n";
    el.scrollTop = el.scrollHeight;
  }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function cat(a, b) { var o = new Uint8Array(a.length + b.length); o.set(a, 0); o.set(b, a.length); return o; }

  function badgeSize() {
    var sel = $("size").value;
    if (sel !== "auto") return parseInt(sel, 10);
    if (state.status && state.status.size) {
      var n = parseInt(String(state.status.size).split(",")[0], 10);
      if (n === 360 || n === 368) return n;
    }
    return 360;
  }

  function onNotify(ev) {
    var d = new Uint8Array(ev.target.value.buffer.slice(0));
    var r = Nn20.parseReplies(cat(state.rx, d));
    state.rx = r.rest;
    r.msgs.forEach(function (m) {
      if (m.text.indexOf("GetPacketSuccess") >= 0) state.acks.push("ok");
      else if (m.text.indexOf("GetPacketFail") >= 0) state.acks.push("fail");
      else if (m.text.length > 30) {
        try { state.status = JSON.parse(m.text); $("status").textContent = JSON.stringify(state.status, null, 1); }
        catch (e) { /* partial JSON */ }
      }
    });
  }

  async function connect() {
    if (!navigator.bluetooth) { log("Web Bluetooth is not available in this browser (use Chrome or Edge, over https or localhost)."); return; }
    try {
      var opts = $("anydev").checked
        ? { acceptAllDevices: true, optionalServices: [SERVICE] }
        : { filters: [{ services: [SERVICE] }], optionalServices: [SERVICE] };
      state.device = await navigator.bluetooth.requestDevice(opts);
      state.device.addEventListener("gattserverdisconnected", function () { log("disconnected"); setConnected(false); });
      log("connecting to " + (state.device.name || "(no name)"));
      var server = await state.device.gatt.connect();
      var svc = await server.getPrimaryService(SERVICE);
      state.write = await svc.getCharacteristic(WRITE);
      var n = await svc.getCharacteristic(NOTIFY);
      n.addEventListener("characteristicvaluechanged", onNotify);
      await n.startNotifications();
      setConnected(true);
      log("connected; waiting for the status push on 0x01F2");
    } catch (e) { log("connect failed: " + e.message); }
  }

  function setConnected(on) {
    $("connect").disabled = on;
    $("disconnect").disabled = !on;
    $("send").disabled = !(on && state.jpeg);
  }

  function disconnect() { if (state.device && state.device.gatt.connected) state.device.gatt.disconnect(); }

  /* centre-crop to a square, black background, circular alpha mask */
  async function renderCrop(file) {
    var size = badgeSize(), bmp = await createImageBitmap(file);
    var c = $("preview"); c.width = size; c.height = size;
    var g = c.getContext("2d");
    g.fillStyle = "#000"; g.fillRect(0, 0, size, size);
    g.save();
    if (!$("square").checked) { g.beginPath(); g.arc(size / 2, size / 2, size / 2, 0, Math.PI * 2); g.clip(); }
    var s = Math.min(bmp.width, bmp.height);
    g.drawImage(bmp, (bmp.width - s) / 2, (bmp.height - s) / 2, s, s, 0, 0, size, size);
    g.restore();
    var blob = await new Promise(function (r) { c.toBlob(r, "image/jpeg", 0.9); });
    state.jpeg = new Uint8Array(await blob.arrayBuffer());
    log("cropped " + size + "x" + size + ", JPEG " + state.jpeg.length + " bytes");
    $("send").disabled = !(state.device && state.device.gatt.connected);
  }

  async function writeFrame(f) { await state.write.writeValueWithoutResponse(f); }

  async function waitAck(ms) {
    var t = Date.now();
    while (Date.now() - t < ms) { if (state.acks.length) return state.acks.shift(); await sleep(10); }
    return "timeout";
  }

  async function send() {
    var interval = Math.max(0, parseInt($("interval").value, 10) || 0);
    var batch = Math.max(1, parseInt($("batch").value, 10) || 1);
    var mtu = Math.max(23, parseInt($("mtu").value, 10) || 23);
    var size = badgeSize();
    var type = Nn20.TYPE_GIF;
    var payload = Nn20.gifContainer([state.jpeg], parseInt($("still").value, 10) || 3000, size, size);
    var frames, tries = 0;
    for (;;) {
      frames = Nn20.buildFrames(type, payload, mtu);
      log("type 5, " + payload.length + " bytes, " + frames.length + " packets of up to " + Nn20.dataPerPacket(mtu) + " data bytes");
      try { await sendFrames(frames, interval, batch); log("done"); return; }
      catch (e) {
        if (tries++ >= 3 || mtu <= 23) { log("send failed: " + e.message); return; }
        mtu = Math.max(23, Math.floor(mtu / 2)); $("mtu").value = mtu;
        log("write error (" + e.message + "); retrying with MTU " + mtu);
      }
    }
  }

  async function sendFrames(frames, interval, batch) {
    var noack = state.status && String(state.status.time_mode) === "1";
    var i = 0, cur = batch, fails = 0;
    state.acks = [];
    while (i < frames.length) {
      var part = frames.slice(i, i + (noack ? 1 : cur));
      state.acks = [];
      for (var k = 0; k < part.length; k++) { await writeFrame(part[k]); await sleep(interval); }
      if (!noack) {
        var good = 0, bad = false;
        for (var j = 0; j < part.length; j++) {
          var r = await waitAck(interval * part.length + 2500);
          if (r === "ok") good++; else { bad = true; break; }
        }
        i += good;
        if (bad) { if (++fails > 3) throw new Error("badge did not acknowledge packet " + i); cur = 1; await sleep(500); }
        else if (cur < batch) cur = Math.min(batch, cur * 2);
      } else i += part.length;
      $("progress").value = Math.floor(100 * i / frames.length);
    }
    await sleep(Math.min(Math.ceil(frames.length / 1000) * 800 + 800, 3000));
  }

  window.addEventListener("DOMContentLoaded", function () {
    $("connect").addEventListener("click", connect);
    $("disconnect").addEventListener("click", disconnect);
    $("send").addEventListener("click", send);
    $("file").addEventListener("change", function (e) { if (e.target.files[0]) renderCrop(e.target.files[0]).catch(function (x) { log("image error: " + x.message); }); });
    $("size").addEventListener("change", function () { var f = $("file").files[0]; if (f) renderCrop(f); });
    $("square").addEventListener("change", function () { var f = $("file").files[0]; if (f) renderCrop(f); });
    if (!navigator.bluetooth) log("Web Bluetooth is not available here; open this page in Chrome or Edge from localhost or https.");
  });
})();
