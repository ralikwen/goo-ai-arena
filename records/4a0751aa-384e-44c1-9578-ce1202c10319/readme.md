# Ralikwen — It's a tower

**13.9 metres · all 300 balls used · standing after five minutes untouched**

## Note

I learned that teaching AI is hard.

![Full structure in the native game](images/full-structure.png)

The tower contains 205 attached balls and 95 balls consumed by legal missing connections. Ralikwen supplied the objective and broad-base, shape and alignment guidance. Codex selected the construction sequence and operated the native game inputs. This is human-and-machine work.

## Repeat the build

Load [the supplied starting setup](setup.md), then open [the rebuilding guide](rebuild.md), then follow [the 297-step placement sequence](rebuild-steps.md) alongside [the successful-build log](events/0001.jsonl). The guide covers the starting setup, supporting-ball identities, camera coordinates, pickup and adapting placements to the game's movement. A second complete reconstruction has not yet been demonstrated.

The log contains only the successful continuous build and its final hold, including recovery actions within that attempt. It includes no earlier failed attempts or task conversation. The manifest briefly credits earlier preparation, but this is not a history of the development process.

`start/pers3.dat` supplies the original prepared starting profile, with [loading instructions](setup.md). `start.json` and `final.json` describe the observed starting and final structures. `save/pers3.dat` is the unchanged native save of the completed tower. The package provides instructions and recorded actions for rebuilding; it includes no audit report, raw observation archive or audit program.

## Image

The single image shows the full structure after reopening the unchanged native save. Only camera position and zoom were adjusted in an isolated viewing copy; there were no construction inputs. `evidence/full-view.json` describes that capture. The height and five-minute hold come from the original successful build.

## Inspect the saved tower

Use a licensed World of Goo 1.6.538 installation in an isolated Linux test home. With the game closed, back up any existing `.WorldOfGoo/pers3.dat` there, then place the attached `save/pers3.dat` at that path. Launch the game, choose the `record-lab` profile and enter World of Goo Corporation. The submitted build ran through Box64 on Linux ARM64. Normal save rounding and movement after reload are possible.

Loading this save inspects the completed tower. Begin from an allowed starting state to repeat its construction.

## Publication

This is the first public publication of the successful build. Its starting profile,
rebuilding instructions, successful-build log, finished save, single image, measured
height and hold describe the same completed run; publication is not another build.
