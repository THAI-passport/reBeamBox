# Ads in the original app, and this client

Analysed: Beambox+ 1.0.14 (static, from the decompiled code and manifest). Nothing here modifies or redistributes the app; this is a description of what the app does and what our client does instead.

## 1. What the original app shows
- [C] No third-party advertising SDK is present. The manifest and code contain no AdMob / Google Mobile Ads, AppLovin, Pangle (ByteDance), Unity Ads, ironSource, Vungle, Mintegral or similar activities, services, meta-data or classes, and no interstitial, rewarded or app-open ad calls.
- [C] Promotional surface 1: a home-screen banner carousel (XBanner library). Items are downloaded from the vendor server (`GET app/api/carousel`); each record has an image URL, an "is redirect" flag and a link URL. Tapping can open a link in the in-app browser (BrowserActivity). This is vendor-run content, not an ad network.
- [C] Promotional surface 2: a store ("mall"), sign-in task and reward screens, community posts and "gold coin" mechanics, all backed by the vendor API. Product pages open in the in-app browser.
- [C] Splash: SplashActivity is the launcher. It only routes deep links (scheme `beamboxapp`, hosts `detail`, `homepage`, `install`) after a 1 s delay; it does not load an ad.
- [C] Tracking-related items: the manifest declares `com.google.android.gms.permission.AD_ID` and the Play install referrer permission; a Facebook SDK (login and share activities) is bundled; the app posts logs to the vendor (`POST log`). The advertising id permission is declared but no ad SDK that would consume it was found in the app's own code [I: it may come from Play Services libraries].
- [C] Backend: https://beambox.cn/nnfamily/ and test host; some option URLs are plain HTTP to a raw IP. Account, community, AI image generation and the device product list all depend on it.

## 2. What this client does
- It contains no ad code, no banner or splash, no analytics, no advertising id access and no Facebook or other third-party SDK. Dependencies are bleak and Pillow only.
- It makes no calls to any vendor backend (no beambox.cn, no raw IP hosts). The only network-free operations are Bluetooth LE to the badge and local file conversion. The device product list is replaced by name filters you can set yourself (`--name`).
- It does not need an account, location permission on Linux, or any phone-side services.
- Because there is nothing to remove, no modification of the original app is involved or provided. Use the original app unchanged if you want its community features; use this client only for sending your own media to your own badge.

## 3. Verify it yourself
```
grep -rn "http" rebeambox/            # no URLs in the client
python -m pytest tests -q              # includes dry-run tests that open no Bluetooth or network sockets
```
