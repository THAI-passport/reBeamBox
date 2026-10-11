# Beambox+ app behaviour (observed statically, v1.0.14)

Notes from the manifest and decompiled code. No app source or assets are reproduced.

## Overview
Companion app for round-screen electronic badges. It sends photos, videos and GIFs to the badge over BLE, with a community, account system and AI image generation around it. Main package: com.example.nn20 (shared with sibling apps by the same vendor). Launcher activity: SplashActivity, then MainActivity.

## Screens and features (by activity)
- Device connection: BluetoothDeviceActivity, PollyConectDeviceActivity, WiFiDeviceActivity, WifiScanActivity (a Wi-Fi path also exists, not studied), DeviceRegulatingctivity (device settings such as brightness).
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
