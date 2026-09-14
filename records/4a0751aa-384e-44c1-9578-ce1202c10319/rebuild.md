# Rebuild Ralikwen — It's a tower

The aim is a broad tower that uses all 300 balls and remains standing. This run reached 13.9 m. The following instructions describe its successful construction; they have not been tested in a second complete build.

## Starting setup

Use World of Goo 1.6.538, World of Goo Corporation, with normal physics and the ruleset declared in `submission.json`. Begin with the native three-ball triangle and 297 loose Drained balls, for 300 material units total. This run used a dedicated equivalent-start profile prepared before launch, rather than collecting the balls through the campaign. `start.json` discloses that setup and the observed starting positions. It is a state description. The original loadable starting profile is now included as `start/pers3.dat`; follow [Starting setup](setup.md) to install it in an isolated game environment. The separate `save/pers3.dat` is the completed tower, not the starting point.

The recorded game ran at 1280×720 through Box64 on Linux ARM64. Native random state was not recorded, so loose-ball positions and timing can differ. In your fresh run, identify the starter triangle as b000 (left foot), b001 (right foot), b002 (apex). Assign each incoming ball the name in the placement table as you use it; native memory addresses and loose-ball pickup order need not match.

## Build in the recorded order

1. Open [the placement sequence](rebuild-steps.md). Each row identifies the incoming ball, the two supporting balls, the intended operation and its release event in [the successful-build log](events/0001.jsonl).
2. Complete actions 1–41 to form the wide, low foundation. Then follow actions 42–297, which fill low supported spaces and add useful missing connections before increasing height. The actual sequence, rather than an idealized triangle, describes the tower in the image.
3. For `attach`, pick up a loose ball and position it so the native preview joins it to both listed supporting balls. For `reinforce`, use a loose donor to create the missing connection between the listed existing balls; this consumes one ball without adding a visible node.
4. Use the table's placement hints relative to the current supporting pair. Confirm the intended native preview before releasing. If it differs, keep holding and adjust the position; do not blindly release at the original screen pixel. After release, allow movement to settle enough to select the next placement. This run waited at least about one second after each release, with additional time spent on pickup, camera movement and preview alignment.

## Camera, pickup and timing

The JSONL `move` and `release` positions are original screen pixels, measured from the upper-left corner. They include native edge panning and cannot be replayed unchanged under a different camera. Pan until the target and supporting pair are clearly visible, then move the pointer away from the edges to stop panning. Use the table's world-relative hints and the live preview to place the ball.

Pickup begins on a left-button press (`pickup_begin`); `pickup_end` records the observation that the ball is held, not a second press. The actual button release is `release`. Its following `state` event describes attachment or donor consumption. Map those ball IDs to your current structure. If a loose ball moves out of reach, reacquire an accessible loose ball and resume the same intended step after confirming what is held. This run used native pickup and camera movement; the whistle was unavailable in its starting profile.

Use the recorded wall and game clocks to understand order and waiting, not as a fixed playback schedule. Movement, settling and preview alignment may take different amounts of time. If the listed connection cannot be offered legally, revisit the current geometry and supporting pair; record any changed sequence as part of your own attempt.

## Finish

The recorded sequence ends with 205 attached balls, 95 consumed reinforcement donors and 502 connections. All 300 material units are used. Release all controls and leave normally advancing gameplay untouched for five minutes to repeat this entry's standing check. Then read the game's height and save through the game. Record your own result; the original 13.9 m is not a guaranteed outcome of replaying timings or coordinates.

Take one native screenshot showing the whole structure. The supplied image was taken after reopening the unchanged finished save with camera-only viewing adjustments, described in `evidence/full-view.json`.

To inspect the existing result, follow the save restoration instructions in [the entry overview](readme.md). Inspection of that save is separate from rebuilding it.
