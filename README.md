# PerfectSync ARKit BlendShape Pose Recorder for Blender

A Blender addon for building the 52 ARKit face blendshapes on a character
by posing face bones (rather than sculpting mesh shape keys by hand),
recording each pose, and baking all 52 into real shape keys in one pass.
Includes left/right mirroring, JSON presets reusable across characters
built on the same rig, and animated reference GIFs shown right in the
panel.

## Preview

![ARKit pose recorder UI in Blender](https://github.com/harlynkingm/ARKit-Pose-Recorder-for-Blender/raw/main/previewImage.png "ARKit pose recorder UI in Blender")

## Requirements

- Blender 4.0+ (tested on 5.1)
- [Pillow](https://pypi.org/project/pillow/), installed into **Blender's
  own bundled Python** (not your system Python) — only needed for the
  inline animated reference preview. Everything else works without it.

### Installing Pillow into Blender's Python

Find Blender's bundled Python (adjust the version/path for your install):

```
"C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe" -m pip install pillow
```

If pip doesn't have write access to that folder, it may silently install
into your user site-packages instead of Blender's own — that's fine, this
addon already checks the user site-packages location itself at startup,
so either location works. To verify Pillow is visible to Blender, check
the "Description" section of any shape in the panel: if Pillow isn't
found, it says so directly rather than failing silently.

## Installation

1. Zip this whole `arkit_pose_recorder` folder (or use the pre-zipped
   copy if you have one).
2. In Blender: Edit > Preferences > Add-ons > Install, select the zip.
3. Enable "ARKit Pose Recorder."
4. The panel appears in the 3D Viewport sidebar (press N), under an
   "ARKit Poses" tab.

## Folder structure

```
arkit_pose_recorder/
├── __init__.py                      addon code
├── README.md                        this file
└── arkit_pose_recorder_gifs/        one <shapeName>.gif per ARKit shape
```

The GIFs folder must stay inside this addon folder and keep this exact
name — the addon looks for it relative to its own install location, so
this whole folder is self-contained and portable (copy it as a unit to
move or back up the addon, gifs included).

## Workflow

### 1. Set up

At the top of the panel, set:
- **Face Armature** — the rig whose bones you'll pose
- **Face Mesh** — the mesh that will receive the 52 baked shape keys

The 52 built-in ARKit shapes populate automatically the first time the
panel draws.

### 2. Pose and save each shape

- Select a shape in the list (hover the small info icon per row for
  tracking/modeling guidance from Apple's ARKit reference).
- Pose the relevant face bones by hand in the viewport.
- Click **Save Pose** — only bones that actually moved from rest get
  stored, so it's fine to touch just a couple of bones per shape.
- **Preview** recalls a saved pose onto the rig for review; **Reset**
  snaps the rig back to rest without touching saved data. Nothing is
  lost by navigating between shapes — only Save Pose writes pose data to file.
- Expand **Description** to see tracking/modeling notes, plus an
  animated reference GIF if Pillow is installed (first expand of a given
  shape takes a moment to decode; cached after that for the session).

### 3. Mirror left/right shapes

- Expand **Bone Mirror Map**, click **Refresh From Saved Poses** to pull
  in bones you've used so far, and assign each one's mirror-side
  counterpart via the search field.
- On any shape with a Left/Right counterpart, a **Mirror to [OtherShape]**
  button appears — it reflects the saved pose through the armature's
  mirror plane (using each bone's own rest orientation, not a naive
  flip) and writes directly into the paired shape's data. Preview the
  result and hand-correct/re-save if a character's asymmetry needs it.

### 4. Apply to the mesh

Once you've saved as many of the 52 as you want, **Apply All Saved to
Mesh** bakes each into a real shape key (creating a Basis key if needed)
and leaves the rig at rest. Re-running it after saving more shapes
overwrites existing shape keys of the same name and adds new ones.

### 5. Reuse across characters

**Load Preset JSON** lets you export all saved bone-pose data to a JSON
file and import it into a different character built on the same rig
(bone names must match) — pose once, reuse everywhere.

## Notes

- Applying a saved pose forces face bones to quaternion rotation mode
  so stored rotations can be written back unambiguously — a minor,
  harmless side effect on rigs that normally use Euler.
- Mirroring assumes each bone's rest orientation is meaningful (doesn't
  require left/right bones to be perfectly symmetric) but treats each
  moved bone independently — correct for the vast majority of face
  shapes, which drive one bone per side per shape.

## Acknowledgements

Much of the data and information for this project came from the following repo:
[52blendshapes-for-VRoid-face](https://github.com/hinzka/52blendshapes-for-VRoid-face)

Additional information and GIFS came from this Google Doc, referenced by the same repo:
[Google Doc](https://docs.google.com/document/d/1L03xvTlsa8pJmjsbOZkJW3U2g-8DnJ4M-kelE4ktKdA/edit?usp=sharing)

Apple's ARKit Face Anchor documentation can be found here:
[ARFaceAnchor.BlendShapeLocation Documentation](https://developer.apple.com/documentation/arkit/arfaceanchor/blendshapelocation)