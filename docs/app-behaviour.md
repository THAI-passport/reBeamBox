# Beambox+ app behaviour (observed statically, v1.0.14)

Notes from the manifest and decompiled code. No app source or assets are reproduced.

## Overview
Companion app for round-screen electronic badges. It sends photos, videos and GIFs to the badge over BLE, with a community, account system and AI image generation around it. Main package: com.example.nn20 (shared with sibling apps by the same vendor). Launcher activity: SplashActivity, then MainActivity.

## Screens and features (by activity)
- Device connection: BluetoothDeviceActivity, PollyConectDeviceActivity, WiFiDeviceActivity, WifiScanActivity (the Wi-Fi path is documented in docs/wifi-protocol.md), DeviceRegulatingctivity (device settings such as brightness).
- Media selection and editing: GalleryActivity, CameraActivity, CameraStreamActivity, CropImageActivity (circular crop), VideoCropActivity, VideoGifActivity, MultiImageCarouselActivity, SingleAddActivity, DoodleCanvasActivity, StickerLibraryActivity(2), FilmCoatingLibraryActivity, BigPictureActivity.
- AI and creative: AiCreateActivity, AiMyCreationActivity, TravelPostcardActivity, TravelPostcardVideoActivity, DanmakuUploadActivity.
- Community: MomentsActivity, PublishActivity, OtherDynamicActivity, ArtworkDetailActivity, CommentDetailActivity, MyFriendsActivity, HistoryActivity.
- Account: UnifiedLoginActivity, RegisterActivity(2), AgeSelectionActivity, verification code, password and profile screens, security and privacy settings, notifications, feedback, about, contact.
- Game/pet style screens: PollyHomeActivity, PollyShopActivity, PollyWorkActivity, PetsNetSetActivity, RoleCardActivity, CharacterRelationshipActivity, GameRecordActivity, GameDetailActivity, TablePartnerActivity, DeviceBrochuresActivity (likely shared with sibling products).

## Main user flow
1. Grant Bluetooth, location and media permissions.
2. Scan and pick a badge (name contains NEO or B-Device); the app connects, negotiates MTU 512 and enables notifications.
3. Choose an image, video or GIF; crop to the circular 360x360 area; frames extracted with FFmpeg or Glide helpers.
4. App converts to JPEG (quality 90) and packs into the badge container, checks free space reported by the badge, then uploads in checksummed packets with ACK pacing.
5. Optional: set brightness, browse badge content (album, watch face, boot animation types exist).

## Permissions (manifest)
Bluetooth connect/scan, fine and coarse location (BLE scanning), camera, media read (images, video, audio, selected media), Wi-Fi state and change, network state, internet, vibrate, wake lock, foreground service, boot completed, activity recognition and step-count health permissions (steps, Xiaomi and OPPO providers), CALL_PHONE, ad ID, Play install referrer and license check. The step and phone permissions are not needed for BLE image upload.

## Third-party components seen
Firebase, Google Play services (auth, cast), Facebook login, Gson, OkHttp, LitePal (database), MMKV, Glide, ijkplayer and FFmpegKit (video), EventBus, Jieli SDKs (Bluetooth connect and OTA).

## Network
Account, community and AI features call vendor servers over HTTP(S). Not analysed here; the badge protocol itself is local BLE.

## Update: transports and device selection (second pass)
- The app has three device transports, chosen when the user taps a scanned device (o7/t6.java): BadgeSdk (names containing NEO or B-Device) using a custom control service plus Jieli RCSP, the older nn20 BLE manager (service 0x01F0) for other products, and a Wi-Fi socket path (192.168.8.1:8080) for Wi-Fi products. Details and byte layouts are in docs/PROTOCOL.md.
- BadgeSdk flow on connect: control GATT, 1.55 s wait, bind (device id, clock and language flags), send time and language, read badge info (screen, picture size, memory), then Jieli link for file transfer.
- Media preparation per path: nn20 scales to 368x368 JPEG q90 and wraps it; BadgeSdk uses the picture size reported by the badge, JPEG for stills and ffmpeg-built MJPEG AVI for animations and video (with optional audio).
- Remote camera: the badge can send a shutter command (0x81) that the CameraActivity listens for; the phone camera screen can also command the badge.
- Other items of note: a payment certificate component is subscribed on a separate GATT characteristic (unrelated to images); the app stores the connected BLE name and last device in MMKV.
