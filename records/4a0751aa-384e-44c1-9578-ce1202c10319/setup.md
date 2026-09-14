# Starting setup

Use [start/pers3.dat](start/pers3.dat) to obtain the same starting configuration used for this successful build. It contains the native-style three-ball starter triangle and 297 loose Drained balls, with no constructed tower or consumed reinforcement donors. The sole player profile is `record-lab`.

This is a prepared, construction-equivalent starting profile, initialized before the original game launch. It is not a claim that the balls were earned through the campaign, and it is not the finished save. These are the unchanged starting-profile bytes from the successful run. The game loaded this file for that run; it has not been newly tested on other game versions or operating systems.

## Load the start

1. Use a licensed **Linux World of Goo 1.6.538** installation. Use a separate Linux test account or an existing isolated game environment with its own player-data home. Keep the game's physics and assets unchanged. The original run used the x86_64 game through Box64 on Linux ARM64.
2. Close the game in that environment. Its player file is `.WorldOfGoo/pers3.dat` inside its home directory. If that file already exists, preserve a backup before replacing it.
3. Download `start/pers3.dat` from this bundle and place it at that player-file location, keeping the filename `pers3.dat`. Do not use `save/pers3.dat`: that separate file contains the completed tower.
4. Launch the game in the same isolated environment, choose **record-lab**, and enter **World of Goo Corporation**. Let normal gameplay settle. You should see only the starter triangle and loose balls, with **300 total material units**. If a finished tower is present, close the game and check that you copied the starting file into the home actually used by this game instance.
5. Begin [the rebuilding guide](rebuild.md). Map the starter's left foot, right foot and apex to b000, b001 and b002. The loose balls may move differently after loading; choose available balls and use the recorded supporting pairs and live previews.

The profile leaves the whistle unavailable, matching the original run. The guide therefore uses pickup and camera movement. The observed `start.json` positions are from advancing gameplay after this file loaded, so they can differ from serialized initial positions. An uncontrolled native RNG also means that reloading does not promise identical timing.

Starting file SHA-256: `12fa0ac7d8bf1ed6c28794c889e71b266425e9bcacc3ffdd6d686fcb20174d1d`.

After rebuilding, save your new result through the game. Retain this downloaded starting file separately if you want to start another attempt.
