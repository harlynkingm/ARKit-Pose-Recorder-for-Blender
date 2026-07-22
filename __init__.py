bl_info = {
    "name": "ARKit Pose Recorder",
    "author": "Max Harlynking",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > ARKit Poses",
    "description": (
        "Manually pose face bones for each of the 52 ARKit shapes, "
        "save/preview/reset each pose, then bake all saved poses into "
        "real mesh shape keys in one pass."
    ),
    "category": "Animation",
}

import json
import os
import site
import sys
import textwrap

import bpy
from bpy.app.handlers import persistent
import bpy.utils.previews
from mathutils import Matrix, Quaternion
from bpy.props import (
    StringProperty,
    FloatVectorProperty,
    CollectionProperty,
    IntProperty,
    PointerProperty,
    BoolProperty,
)
from bpy.types import PropertyGroup, Operator, Panel, UIList, Object

# Blender's embedded Python doesn't check the user site-packages directory
# by default, so a plain "pip install" from a terminal (which does check
# it, and silently falls back there without admin write access to
# Blender's own Program Files folder) can be invisible to Blender even
# though the exact same python.exe sees it fine outside Blender.
_user_site = site.getusersitepackages()
if _user_site not in sys.path:
    sys.path.append(_user_site)

try:
    from PIL import Image as PILImage, ImageSequence
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Built-in ARKit 52 shape definitions: (name, tracking_note, modeling_hint)
# Paraphrased/condensed from "Description of 52 blendshapes for iPhone face
# Tracking" for use as in-addon guidance while posing.
# ---------------------------------------------------------------------------
ARKIT_52 = [
    ("browInnerUp", "Raise the inside of the eyebrows. Do not move the ends of the eyebrows.",
     "4 eyebrow shapes total (browInnerUp, browDownL/R, browOuterUpL/R). Keep eyebrow end position fixed. Combine with browOuterUp at 100% each for a 'surprised eyebrow' look."),
    ("browDownLeft", "Lower the entire left eyebrow.",
     "Tilt and lower the whole left eyebrow. Push the upper eyelid down slightly, but don't let it bury the eye when combined with blink."),
    ("browDownRight", "Lower the entire right eyebrow.",
     "Same as browDownLeft, mirrored."),
    ("browOuterUpLeft", "Raise the outside of the left eyebrow.",
     "Keep the eyebrow 'head' (inner start) position fixed. Slightly lift the upper eyelid at the outer eye corner."),
    ("browOuterUpRight", "Raise the outside of the right eyebrow.",
     "Same as browOuterUpLeft, mirrored."),
    ("eyeLookUpLeft", "Turn the pupil of the left eye upward.",
     "Look through the center of the upper eyelid; lift the center of the lower eyelid slightly."),
    ("eyeLookUpRight", "Turn the pupil of the right eye upward.",
     "Same as eyeLookUpLeft, mirrored."),
    ("eyeLookDownLeft", "Turn the pupil of the left eye downward.",
     "Lower the center of the upper and lower eyelid slightly to follow the eye."),
    ("eyeLookDownRight", "Turn the pupil of the right eye downward.",
     "Same as eyeLookDownLeft, mirrored."),
    ("eyeLookInLeft", "Turn the pupil of the left eye inward (toward nose).",
     "Move eyelid vertices toward the top of the eye only, weighted toward the inner corner."),
    ("eyeLookInRight", "Turn the pupil of the right eye inward (toward nose).",
     "Same as eyeLookInLeft, mirrored."),
    ("eyeLookOutLeft", "Turn the pupil of the left eye outward (toward ear).",
     "Move only the outer eye corner, weighted toward that corner."),
    ("eyeLookOutRight", "Turn the pupil of the right eye outward (toward ear).",
     "Same as eyeLookOutLeft, mirrored."),
    ("eyeBlinkLeft", "Close the left eye.",
     "Normal blink closure (not a smiling 'joy eye' close). Consider a slight pupil scale-down to avoid clipping through the closed lid."),
    ("eyeBlinkRight", "Close the right eye.",
     "Same as eyeBlinkLeft, mirrored."),
    ("eyeSquintLeft", "Smile with the left eye.",
     "Lift the lower eyelid (not a fully closed 'joy eye'). Pupil stays visible. Careful: on big-eyed characters this can elongate the face."),
    ("eyeSquintRight", "Smile with the right eye.",
     "Same as eyeSquintLeft, mirrored."),
    ("eyeWideLeft", "Widen the left eye.",
     "Open the eyelid wide; on large-eyed characters you may need to shrink the pupil slightly so sclera stays visible."),
    ("eyeWideRight", "Widen the right eye.",
     "Same as eyeWideLeft, mirrored."),
    ("cheekPuff", "Puff both cheeks out.",
     "Puff visibly from the front; lips slightly forward/pointed. Don't over-narrow the mouth or it collapses when combined with mouthPucker."),
    ("cheekSquintLeft", "Pull up the left cheek (smiling eye-cheek).",
     "Prefer moving mouth corner / lower eyelid over the whole cheek for cartoon-style faces. Side stretch expands the mouth when smiling."),
    ("cheekSquintRight", "Pull up the right cheek.",
     "Same as cheekSquintLeft, mirrored."),
    ("noseSneerLeft", "Scrunch/frown the left side of the nose and eyebrow.",
     "Eyebrow lowers and moves inward as an accompanying motion; keep overall eyebrow position, don't over-lower since it combines with browDown."),
    ("noseSneerRight", "Scrunch/frown the right side of the nose and eyebrow.",
     "Same as noseSneerLeft, mirrored."),
    ("jawOpen", "Open the mouth via the jaw.",
     "Make the opening generous, a small jawOpen barely reads. Pairs with mouthClose (both 100% = jaw open, mouth shut = chewing motion). Only jaw* shapes should move the teeth."),
    ("jawForward", "Move the jaw forward.",
     "Move jaw, tongue, and lower teeth together."),
    ("jawLeft", "Move the jaw left.",
     "Move jaw, tongue, and lower teeth together. Usually a small, controlled motion."),
    ("jawRight", "Move the jaw right.",
     "Same as jawLeft, mirrored."),
    ("mouthFunnel", "Lips pouted/funneled, as in saying 'Woo'.",
     "Narrow mouth corners, thrust lips out, slightly show teeth. Don't move teeth. Slightly lift the tongue tip."),
    ("mouthPucker", "Narrow the width of the lips (kiss-ish shape, no funnel).",
     "The narrower the lips, the more forward/full they read. Combine with mouthFunnel for a kissing mouth. Narrow the tongue too so mouth corners don't clip."),
    ("mouthLeft", "Move the entire mouth left (not just corners).",
     "Move the whole mouth, not just corners; don't move teeth. Let the tongue follow naturally."),
    ("mouthRight", "Move the entire mouth right.",
     "Same as mouthLeft, mirrored."),
    ("mouthRollUpper", "Roll/pinch the upper lip inward between the teeth.",
     "Keep the edge of the upper lip visible so the mouth doesn't disappear on toon-style texture models. Pairs with mouthRollLower."),
    ("mouthRollLower", "Roll/pinch the lower lip inward between the teeth.",
     "Same idea as mouthRollUpper, the two pair together."),
    ("mouthShrugUpper", "Lift the upper lip tightly (shrug).",
     "Pairs with mouthShrugLower for a closed frowning mouth, and with mouthPress for a tightly-closed mouth."),
    ("mouthShrugLower", "Lift the lower lip tightly (shrug).",
     "Pairs with mouthShrugUpper. Keep corner-pulling motion on one lip only, not split evenly, or corners rattle."),
    ("mouthClose", "Close the mouth while the jaw stays open.",
     "Looks broken as a standalone shape but is correct, combine with jawOpen at 100/100 for 'jaw open, mouth shut'. Doesn't work well alone in live tracking."),
    ("mouthSmileLeft", "Raise the left corner of the mouth (smile).",
     "Don't move teeth. Balance so raising the corner doesn't shift the whole mouth up, lower it slightly to compensate if needed."),
    ("mouthSmileRight", "Raise the right corner of the mouth.",
     "Same as mouthSmileLeft, mirrored."),
    ("mouthFrownLeft", "Lower the left corner of the mouth.",
     "Mainly reads with the mouth closed; should look natural combined with jawOpen."),
    ("mouthFrownRight", "Lower the right corner of the mouth.",
     "Same as mouthFrownLeft, mirrored."),
    ("mouthDimpleLeft", "Pull the left mouth corner backward/wider.",
     "Stretch the middle of the lips rather than the corner itself, so it composites cleanly with mouthSmile."),
    ("mouthDimpleRight", "Pull the right mouth corner backward/wider.",
     "Same as mouthDimpleLeft, mirrored."),
    ("mouthUpperUpLeft", "Lift the left side of the upper lip, baring teeth.",
     "Don't move teeth. Upper lip corner lifts more than center, gradient the left/right split so it doesn't look mechanical."),
    ("mouthUpperUpRight", "Lift the right side of the upper lip.",
     "Same as mouthUpperUpLeft, mirrored."),
    ("mouthLowerDownLeft", "Pull the left side of the lower lip down, baring teeth.",
     "Don't move teeth. Lower lip center moves down more than the corners, gradient the split."),
    ("mouthLowerDownRight", "Pull the right side of the lower lip down.",
     "Same as mouthLowerDownLeft, mirrored."),
    ("mouthPressLeft", "With the mouth closed, push/squash the left corner up tight (duck mouth).",
     "Easiest to control since it only works with the mouth squeezed shut. Keep symmetric if aiming for a cat/duck-mouth look."),
    ("mouthPressRight", "With the mouth closed, push/squash the right corner up tight.",
     "Same as mouthPressLeft, mirrored."),
    ("mouthStretchLeft", "Pull the left mouth corner down/wide to open the mouth further.",
     "Build from a 100% jawOpen pose, pull the corner down there, then back jawOpen off to get the right isolated shape."),
    ("mouthStretchRight", "Pull the right mouth corner down/wide.",
     "Same as mouthStretchLeft, mirrored."),
    ("tongueOut", "Stick the tongue straight out.",
     "Downward bend of the tongue when the mouth is open is handled by combining with jawOpen, adjust width so the tongue arch crosses the lower lip correctly."),
]

assert len(ARKIT_52) == 52, "ARKIT_52 must contain exactly 52 entries"

EPS = 1e-4


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

class ARKitBoneDelta(PropertyGroup):
    bone_name: StringProperty(name="Bone")
    loc: FloatVectorProperty(name="Location", size=3, subtype='TRANSLATION')
    rot: FloatVectorProperty(name="Rotation Quaternion", size=4, default=(1.0, 0.0, 0.0, 0.0))
    scale: FloatVectorProperty(name="Scale", size=3, default=(1.0, 1.0, 1.0))


class ARKitShapeDef(PropertyGroup):
    shape_name: StringProperty(name="Shape")
    tracking_note: StringProperty(name="Tracking Note")
    modeling_hint: StringProperty(name="Modeling Hint")
    is_saved: BoolProperty(name="Saved", default=False)
    bone_deltas: CollectionProperty(type=ARKitBoneDelta)


class ARKitBonePair(PropertyGroup):
    bone_name: StringProperty(name="Bone")
    mirror_bone_name: StringProperty(name="Mirror Bone")


def poll_armature(self, obj):
    return obj.type == 'ARMATURE'


def poll_mesh(self, obj):
    return obj.type == 'MESH'

def _on_show_description_changed(self, context):
    if self.show_description:
        start_preview_timer()


def _on_active_index_changed(self, context):
    if self.shapes:
        _frame_indices[self.shapes[self.active_index].shape_name] = 0
    if self.show_description:
        start_preview_timer()

class ARKitRecorderSettings(PropertyGroup):
    armature: PointerProperty(name="Face Armature", type=Object, poll=poll_armature)
    mesh: PointerProperty(name="Face Mesh", type=Object, poll=poll_mesh)
    shapes: CollectionProperty(type=ARKitShapeDef)
    active_index: IntProperty(default=0, update=_on_active_index_changed)
    json_path: StringProperty(
        name="Presets File",
        description="JSON file to save/load bone-pose data for all 52 shapes",
        subtype='FILE_PATH',
        default="//arkit_shapes.json",
    )
    show_json_section: BoolProperty(name="Load Preset JSON", default=False)
    show_description: BoolProperty(name="Description", default=False, update=_on_show_description_changed)
    bone_pairs: CollectionProperty(type=ARKitBonePair)
    show_bone_map: BoolProperty(name="Bone Mirror Map", default=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def reset_pose_to_rest(armature_obj):
    for pb in armature_obj.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)


def apply_stored_pose(armature_obj, shape):
    reset_pose_to_rest(armature_obj)
    for entry in shape.bone_deltas:
        pb = armature_obj.pose.bones.get(entry.bone_name)
        if pb is None:
            continue
        # Force quaternion rotation so we can write back the captured
        # rotation unambiguously, regardless of the bone's usual mode.
        pb.rotation_mode = 'QUATERNION'
        pb.location = entry.loc
        pb.rotation_quaternion = entry.rot
        pb.scale = entry.scale


def get_mirror_target(shape_name):
    """Return the paired Left/Right shape name for a built-in ARKit shape,
    or '' if it's a center shape with no mirror counterpart."""
    if shape_name.endswith("Left"):
        return shape_name[:-4] + "Right"
    if shape_name.endswith("Right"):
        return shape_name[:-5] + "Left"
    return ""


REFERENCE_GIF_SUBDIR = "arkit_pose_recorder_gifs"
 
 
def get_reference_gif_path(shape_name):
    """Path to the reference GIF for a shape, expected as a sibling folder
    of this addon file named arkit_pose_recorder_gifs/<shape_name>.gif"""
    addon_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(addon_dir, REFERENCE_GIF_SUBDIR, f"{shape_name}.gif")

# ---------------------------------------------------------------------------
# Inline animated preview (Description section)
#
# Confirmed via testing: bpy.utils.previews is a static-thumbnail system
# (MOVIE type included), and Blender's own Image/MovieClip APIs don't
# expose real per-frame pixel access in a way we could drive headlessly.
# So: Pillow decodes each shape's GIF into individual frames (downscaled
# and frame-capped to keep memory reasonable), each frame is written
# in-memory into a custom preview via pcoll.new() + image_pixels_float
# (no PNGs written to disk), cached per shape for the Blender session,
# and a timer advances which cached frame is shown + redraws while
# Description is expanded.
# ---------------------------------------------------------------------------
 
MAX_PREVIEW_FRAMES = 24   # subsample longer gifs down to this many frames
PREVIEW_THUMB_SIZE = 200  # px, long edge
ANIM_INTERVAL = 0.12      # seconds between frames

_preview_collection = None

_shape_frame_icons = {}   # shape_name -> [icon_id, ...] ([] = no gif / failed / no Pillow)
_frame_indices = {}       # shape_name -> current frame index
 
def get_previews():
    global _preview_collection
    if _preview_collection is None:
        _preview_collection = bpy.utils.previews.new()
    return _preview_collection
 
 
def decode_shape_frames(shape_name):
    """Lazily decode + cache a shape's reference GIF into a list of
    icon_ids using Pillow. Returns [] if Pillow isn't available, the
    file is missing, or decoding fails for any reason."""
    if shape_name in _shape_frame_icons:
        return _shape_frame_icons[shape_name]
 
    icon_ids = []
    if PIL_AVAILABLE:
        gif_path = get_reference_gif_path(shape_name)
        if os.path.isfile(gif_path):
            try:
                icon_ids = _decode_gif_to_icons(shape_name, gif_path)
            except Exception as e:
                print(f"[ARKit Recorder] Failed decoding {gif_path}: {e}")
                icon_ids = []
 
    _shape_frame_icons[shape_name] = icon_ids
    return icon_ids
 
 
def _decode_gif_to_icons(shape_name, gif_path):
    pcoll = get_previews()
    im = PILImage.open(gif_path)

    # ImageSequence.Iterator reuses the same underlying image object across
    # frames (calling .seek() between yields), so collecting raw yields into
    # a list first and converting them later would silently give every
    # entry the SAME (last) frame's data. Converting to RGBA immediately,
    # during iteration, is what actually snapshots each frame independently.
    all_frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(im)]

    total = len(all_frames)

    if total > MAX_PREVIEW_FRAMES:
        step = total / MAX_PREVIEW_FRAMES
        indices = [int(i * step) for i in range(MAX_PREVIEW_FRAMES)]
    else:
        indices = list(range(total))
 
    icon_ids = []
    for i, frame_idx in enumerate(indices):
        frame = all_frames[frame_idx].copy()
        frame.thumbnail((PREVIEW_THUMB_SIZE, PREVIEW_THUMB_SIZE))
        # Blender's pixel buffers are bottom-to-top; PIL's are top-to-bottom.
        frame = frame.transpose(PILImage.FLIP_TOP_BOTTOM)
 
        w, h = frame.size
        pixels = [v / 255.0 for v in frame.tobytes()]
 
        key = f"{shape_name}_{i:03d}"
        preview = pcoll.new(key)
        preview.image_size = (w, h)
        preview.image_pixels_float[:] = pixels
        icon_ids.append(preview.icon_id)
 
    return icon_ids
 
 
def _advance_preview_frame():
    settings = bpy.context.scene.arkit_recorder
    if not settings.show_description or not settings.shapes:
        return None  # stop ticking; restarted on demand when needed again
 
    shape = settings.shapes[settings.active_index]
    icons = decode_shape_frames(shape.shape_name)
    if icons:
        idx = _frame_indices.get(shape.shape_name, 0)
        _frame_indices[shape.shape_name] = (idx + 1) % len(icons)
 
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
 
    return ANIM_INTERVAL
 
 
def start_preview_timer():
    if not bpy.app.timers.is_registered(_advance_preview_frame):
        bpy.app.timers.register(_advance_preview_frame, first_interval=ANIM_INTERVAL)
 
 
def stop_preview_timer():
    if bpy.app.timers.is_registered(_advance_preview_frame):
        bpy.app.timers.unregister(_advance_preview_frame)
 
 
def clear_preview_collections():
    global _preview_collection
    if _preview_collection is not None:
        bpy.utils.previews.remove(_preview_collection)
        _preview_collection = None
    _shape_frame_icons.clear()
    _frame_indices.clear()


MIRROR_X = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))


def compose_matrix(loc, rot_wxyz, scale):
    t = Matrix.Translation(loc)
    r = Quaternion(rot_wxyz).to_matrix().to_4x4()
    s = Matrix.Diagonal((scale[0], scale[1], scale[2], 1.0))
    return t @ r @ s


def mirror_bone_delta(entry, source_bone, target_bone):
    """Reflect a stored bone-local pose delta from source_bone onto
    target_bone through the armature's X=0 mirror plane, using each
    bone's own rest orientation rather than assuming naive symmetry."""
    basis_src = compose_matrix(entry.loc, entry.rot, entry.scale)
    rest_src = source_bone.matrix_local
    rest_tgt = target_bone.matrix_local

    posed_armature_src = rest_src @ basis_src
    posed_armature_tgt = MIRROR_X @ posed_armature_src @ MIRROR_X
    basis_tgt = rest_tgt.inverted() @ posed_armature_tgt

    loc, rot, scale = basis_tgt.decompose()
    return loc, rot, scale


def populate_default_shapes(settings):
    """(Re)fill settings.shapes with the 52 built-in ARKit definitions."""
    settings.shapes.clear()
    for name, tracking_note, hint in ARKIT_52:
        item = settings.shapes.add()
        item.shape_name = name
        item.tracking_note = tracking_note
        item.modeling_hint = hint
    settings.active_index = 0


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class ARKIT_OT_hint_label(Operator):
    """Hover for this shape's tracking + modeling guidance"""
    bl_idname = "arkit.hint_label"
    bl_label = ""
    bl_options = {'INTERNAL'}

    hint_text: StringProperty()

    @classmethod
    def description(cls, context, properties):
        return properties.hint_text

    def execute(self, context):
        return {'FINISHED'}


class ARKIT_OT_init_list(Operator):
    bl_idname = "arkit.init_shape_list"
    bl_label = "Load 52 ARKit Shapes"
    bl_description = "Populate the list with the 52 built-in ARKit shapes and their guidance notes"

    def execute(self, context):
        settings = context.scene.arkit_recorder
        populate_default_shapes(settings)
        self.report({'INFO'}, "Loaded 52 ARKit shape definitions")
        return {'FINISHED'}


class ARKIT_OT_save_pose(Operator):
    bl_idname = "arkit.save_pose"
    bl_label = "Save Pose"
    bl_description = "Store the current bone pose (only bones you've moved) as this shape's data"

    def execute(self, context):
        settings = context.scene.arkit_recorder
        armature_obj = settings.armature
        if armature_obj is None or armature_obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Set a Face Armature first")
            return {'CANCELLED'}
        if not settings.shapes:
            self.report({'ERROR'}, "Load the shape list first")
            return {'CANCELLED'}

        shape = settings.shapes[settings.active_index]
        shape.bone_deltas.clear()

        saved_count = 0
        for pb in armature_obj.pose.bones:
            loc = pb.matrix_basis.to_translation()
            rot = pb.matrix_basis.to_quaternion()
            scl = pb.matrix_basis.to_scale()
            moved = (
                loc.length > EPS
                or abs(rot.w - 1.0) > EPS or abs(rot.x) > EPS
                or abs(rot.y) > EPS or abs(rot.z) > EPS
                or abs(scl.x - 1.0) > EPS or abs(scl.y - 1.0) > EPS or abs(scl.z - 1.0) > EPS
            )
            if not moved:
                continue
            entry = shape.bone_deltas.add()
            entry.bone_name = pb.name
            entry.loc = loc
            entry.rot = (rot.w, rot.x, rot.y, rot.z)
            entry.scale = scl
            saved_count += 1

        shape.is_saved = saved_count > 0
        if saved_count == 0:
            self.report({'WARNING'}, "No bones were moved from rest, nothing saved")
        else:
            self.report({'INFO'}, f"Saved {saved_count} bone transform(s) for '{shape.shape_name}'")
        return {'FINISHED'}


class ARKIT_OT_refresh_bone_pairs(Operator):
    bl_idname = "arkit.refresh_bone_pairs"
    bl_label = "Refresh From Saved Poses"
    bl_description = "Scan all saved shapes and add any bones not already in the mirror map"

    def execute(self, context):
        settings = context.scene.arkit_recorder
        existing = {p.bone_name for p in settings.bone_pairs}
        added = 0
        for shape in settings.shapes:
            for entry in shape.bone_deltas:
                if entry.bone_name in existing:
                    continue
                pair = settings.bone_pairs.add()
                pair.bone_name = entry.bone_name
                pair.mirror_bone_name = ""
                existing.add(entry.bone_name)
                added += 1
        self.report({'INFO'}, f"Added {added} bone(s) to the mirror map" if added else "No new bones found")
        return {'FINISHED'}


class ARKIT_OT_mirror_shape(Operator):
    bl_idname = "arkit.mirror_shape"
    bl_label = "Mirror to Other Side"
    bl_description = "Reflect this shape's saved bone pose onto its Left/Right counterpart"

    def execute(self, context):
        settings = context.scene.arkit_recorder
        armature_obj = settings.armature
        if armature_obj is None or armature_obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Set a Face Armature first")
            return {'CANCELLED'}

        source = settings.shapes[settings.active_index]
        target_name = get_mirror_target(source.shape_name)
        if not target_name:
            self.report({'ERROR'}, f"'{source.shape_name}' has no Left/Right counterpart")
            return {'CANCELLED'}
        if not source.is_saved:
            self.report({'ERROR'}, "This shape has no saved pose to mirror")
            return {'CANCELLED'}

        target = next((s for s in settings.shapes if s.shape_name == target_name), None)
        if target is None:
            self.report({'ERROR'}, f"Target shape '{target_name}' not found in list")
            return {'CANCELLED'}

        pair_map = {p.bone_name: p.mirror_bone_name for p in settings.bone_pairs if p.mirror_bone_name}
        bones = armature_obj.data.bones

        mirrored = 0
        skipped = []
        for entry in source.bone_deltas:
            mirror_name = pair_map.get(entry.bone_name)
            if not mirror_name:
                skipped.append(entry.bone_name)
                continue
            source_bone = bones.get(entry.bone_name)
            target_bone = bones.get(mirror_name)
            if source_bone is None or target_bone is None:
                skipped.append(entry.bone_name)
                continue

            loc, rot, scale = mirror_bone_delta(entry, source_bone, target_bone)

            existing_entry = next((e for e in target.bone_deltas if e.bone_name == mirror_name), None)
            if existing_entry is None:
                existing_entry = target.bone_deltas.add()
                existing_entry.bone_name = mirror_name
            existing_entry.loc = loc
            existing_entry.rot = (rot.w, rot.x, rot.y, rot.z)
            existing_entry.scale = scale
            mirrored += 1

        if mirrored == 0:
            self.report({'ERROR'}, "No bones were mirrored, check the Bone Mirror Map")
            return {'CANCELLED'}

        target.is_saved = True
        msg = f"Mirrored {mirrored} bone(s) into '{target_name}'."
        if skipped:
            msg += f" Skipped (no mirror mapping): {', '.join(skipped)}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class ARKIT_OT_preview_pose(Operator):
    bl_idname = "arkit.preview_pose"
    bl_label = "Preview"
    bl_description = "Apply this shape's saved bone pose to the rig for review"

    def execute(self, context):
        settings = context.scene.arkit_recorder
        armature_obj = settings.armature
        if armature_obj is None or armature_obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Set a Face Armature first")
            return {'CANCELLED'}
        shape = settings.shapes[settings.active_index]
        if not shape.is_saved:
            self.report({'WARNING'}, "No saved pose for this shape yet")
            return {'CANCELLED'}
        apply_stored_pose(armature_obj, shape)
        return {'FINISHED'}


class ARKIT_OT_reset_pose(Operator):
    bl_idname = "arkit.reset_pose"
    bl_label = "Reset"
    bl_description = "Reset the armature to rest pose (does not delete any saved data)"

    def execute(self, context):
        settings = context.scene.arkit_recorder
        armature_obj = settings.armature
        if armature_obj is None or armature_obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Set a Face Armature first")
            return {'CANCELLED'}
        reset_pose_to_rest(armature_obj)
        return {'FINISHED'}


class ARKIT_OT_apply_all(Operator):
    bl_idname = "arkit.apply_all"
    bl_label = "Apply All Saved to Mesh"
    bl_description = "Bake every saved shape's bone pose into a real shape key on the mesh, in order"

    def execute(self, context):
        settings = context.scene.arkit_recorder
        armature_obj = settings.armature
        mesh_obj = settings.mesh
        if armature_obj is None or armature_obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Set a Face Armature first")
            return {'CANCELLED'}
        if mesh_obj is None or mesh_obj.type != 'MESH':
            self.report({'ERROR'}, "Set a Face Mesh first")
            return {'CANCELLED'}

        saved_shapes = [s for s in settings.shapes if s.is_saved]
        if not saved_shapes:
            self.report({'ERROR'}, "No shapes have a saved pose yet")
            return {'CANCELLED'}

        reset_pose_to_rest(armature_obj)
        if mesh_obj.data.shape_keys is None or "Basis" not in mesh_obj.data.shape_keys.key_blocks:
            mesh_obj.shape_key_add(name="Basis", from_mix=False)

        reset_pose_to_rest(armature_obj)
        baked = 0
        skipped = []

        for shape in settings.shapes:
            if not shape.is_saved:
                skipped.append(shape.shape_name)
                continue

            apply_stored_pose(armature_obj, shape)
            context.view_layer.update()

            depsgraph = context.evaluated_depsgraph_get()
            obj_eval = mesh_obj.evaluated_get(depsgraph)
            mesh_eval = obj_eval.to_mesh()

            existing = None
            if mesh_obj.data.shape_keys:
                existing = mesh_obj.data.shape_keys.key_blocks.get(shape.shape_name)
            key_block = existing if existing else mesh_obj.shape_key_add(name=shape.shape_name, from_mix=False)

            if len(mesh_eval.vertices) != len(key_block.data):
                self.report({'ERROR'}, f"Vertex count mismatch baking '{shape.shape_name}', aborting")
                obj_eval.to_mesh_clear()
                reset_pose_to_rest(armature_obj)
                return {'CANCELLED'}

            for i, v in enumerate(mesh_eval.vertices):
                key_block.data[i].co = v.co

            obj_eval.to_mesh_clear()
            baked += 1
            key_block.value = 0.0
            reset_pose_to_rest(armature_obj)

        reset_pose_to_rest(armature_obj)
        msg = f"Baked {baked} shape key(s)."
        if skipped:
            msg += f" Skipped: {', '.join(skipped)}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class ARKIT_OT_export_json(Operator):
    bl_idname = "arkit.export_json"
    bl_label = "Export JSON"
    bl_description = "Write all saved shapes' bone-pose data to the presets file"

    def execute(self, context):
        settings = context.scene.arkit_recorder
        if not settings.json_path:
            self.report({'ERROR'}, "Set a presets file path first")
            return {'CANCELLED'}

        saved_shapes = [s for s in settings.shapes if s.is_saved]
        if not saved_shapes:
            self.report({'ERROR'}, "No shapes have a saved pose yet")
            return {'CANCELLED'}

        data = {}
        for shape in saved_shapes:
            data[shape.shape_name] = [
                {
                    "bone": entry.bone_name,
                    "loc": list(entry.loc),
                    "rot": list(entry.rot),
                    "scale": list(entry.scale),
                }
                for entry in shape.bone_deltas
            ]

        abs_path = bpy.path.abspath(settings.json_path)
        try:
            with open(abs_path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            self.report({'ERROR'}, f"Could not write file: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Exported {len(saved_shapes)} shape(s) to {abs_path}")
        return {'FINISHED'}


class ARKIT_OT_import_json(Operator):
    bl_idname = "arkit.import_json"
    bl_label = "Import JSON"
    bl_description = "Load bone-pose data from the presets file onto the current shape list"

    def execute(self, context):
        settings = context.scene.arkit_recorder
        if not settings.json_path:
            self.report({'ERROR'}, "Set a presets file path first")
            return {'CANCELLED'}

        abs_path = bpy.path.abspath(settings.json_path)
        try:
            with open(abs_path, "r") as f:
                data = json.load(f)
        except OSError as e:
            self.report({'ERROR'}, f"Could not read file: {e}")
            return {'CANCELLED'}
        except json.JSONDecodeError as e:
            self.report({'ERROR'}, f"File is not valid JSON: {e}")
            return {'CANCELLED'}

        # Make sure the built-in list exists so names have somewhere to land.
        if not settings.shapes:
            populate_default_shapes(settings)

        matched = 0
        unmatched = []
        for shape_name, bones in data.items():
            shape = next((s for s in settings.shapes if s.shape_name == shape_name), None)
            if shape is None:
                unmatched.append(shape_name)
                continue
            shape.bone_deltas.clear()
            for b in bones:
                entry = shape.bone_deltas.add()
                entry.bone_name = b.get("bone", "")
                entry.loc = b.get("loc", [0.0, 0.0, 0.0])
                entry.rot = b.get("rot", [1.0, 0.0, 0.0, 0.0])
                entry.scale = b.get("scale", [1.0, 1.0, 1.0])
            shape.is_saved = len(shape.bone_deltas) > 0
            matched += 1

        msg = f"Imported {matched} shape(s) from {abs_path}."
        if unmatched:
            msg += f" Unrecognized names skipped: {', '.join(unmatched)}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class ARKIT_UL_shapes(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        status_icon = 'CHECKMARK' if item.is_saved else 'RADIOBUT_OFF'
        label_text = item.shape_name
        if item.is_saved:
            label_text += f"  ({len(item.bone_deltas)})"
        # Plain label so clicking the row still triggers normal row selection.
        row.label(text=label_text, icon=status_icon)
        # Small icon-only button just for the hover tooltip, doesn't cover
        # the rest of the row so it can't swallow row-select clicks.
        hint_op = row.operator(
            "arkit.hint_label",
            text="",
            icon='INFO',
            emboss=False,
        )
        hint_op.hint_text = f"Tracking: {item.tracking_note}\n\nModeling: {item.modeling_hint}"


class ARKIT_PT_panel(Panel):
    bl_label = "ARKit Pose Recorder"
    bl_idname = "ARKIT_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ARKit Poses"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.arkit_recorder

        if settings.show_description:
            start_preview_timer()

        json_header = layout.row(align=True)
        json_icon = 'TRIA_DOWN' if settings.show_json_section else 'TRIA_RIGHT'
        json_header.prop(settings, "show_json_section", icon=json_icon, text="Load Preset JSON:", emboss=False)
        if settings.show_json_section:
            json_box = layout.box()
            json_box.prop(settings, "json_path", text="")
            row = json_box.row(align=True)
            row.operator("arkit.export_json", icon='EXPORT')
            row.operator("arkit.import_json", icon='IMPORT')

        layout.separator()

        map_header = layout.row(align=True)
        map_icon = 'TRIA_DOWN' if settings.show_bone_map else 'TRIA_RIGHT'
        map_header.prop(settings, "show_bone_map", icon=map_icon, text="Bone Mirror Map", emboss=False)
        if settings.show_bone_map:
            map_box = layout.box()
            map_box.operator("arkit.refresh_bone_pairs", icon='FILE_REFRESH')
            if not settings.bone_pairs:
                map_box.label(text="No bones yet, save a pose first.")
            elif settings.armature is None:
                map_box.label(text="Set a Face Armature above to pick mirror bones.", icon='ERROR')
            else:
                for pair in settings.bone_pairs:
                    prow = map_box.row(align=True)
                    prow.label(text=pair.bone_name)
                    prow.prop_search(pair, "mirror_bone_name", settings.armature.pose, "bones", text="")

        layout.separator()

        col = layout.column()
        col.prop(settings, "armature")
        col.prop(settings, "mesh")

        layout.separator()

        if not settings.shapes:
            layout.operator("arkit.init_shape_list", icon='IMPORT')
            return

        layout.template_list(
            "ARKIT_UL_shapes", "", settings, "shapes", settings, "active_index", rows=12
        )

        active = settings.shapes[settings.active_index]
        box = layout.box()
        box.label(text=f"Selected: {active.shape_name}", icon='BONE_DATA')

        desc_header = box.row(align=True)
        desc_icon = 'TRIA_DOWN' if settings.show_description else 'TRIA_RIGHT'
        desc_header.prop(settings, "show_description", icon=desc_icon, text="Description", emboss=False)
        if settings.show_description:
            desc_box = box.box()
            desc_col = desc_box.column(align=True)
            desc_col.label(text="Tracking:")
            for line in textwrap.wrap(active.tracking_note, width=40):
                desc_col.label(text=line)
            desc_col.separator()
            desc_col.label(text="Modeling:")
            for line in textwrap.wrap(active.modeling_hint, width=40):
                desc_col.label(text=line)

            desc_col.separator()
            if not PIL_AVAILABLE:
                desc_col.label(text="Pillow not installed in Blender's Python", icon='ERROR')
            else:
                icons = decode_shape_frames(active.shape_name)
                if icons:
                    idx = _frame_indices.get(active.shape_name, 0) % len(icons)
                    desc_col.template_icon(icon_value=icons[idx], scale=6.0)
                else:
                    desc_col.label(text="(no reference gif found for this shape)", icon='INFO')

        if active.is_saved:
            box.label(text=f"Saved: {len(active.bone_deltas)} bone(s) moved", icon='CHECKMARK')
        else:
            box.label(text="Not yet saved", icon='RADIOBUT_OFF')

        row = box.row(align=True)
        row.operator("arkit.preview_pose", icon='HIDE_OFF')
        row.operator("arkit.reset_pose", icon='LOOP_BACK')
        row.operator("arkit.save_pose", icon='FILE_TICK')

        mirror_target = get_mirror_target(active.shape_name)
        if mirror_target:
            box.operator(
                "arkit.mirror_shape",
                text=f"Mirror to {mirror_target}",
                icon='MOD_MIRROR',
            )

        layout.separator()
        saved_n = sum(1 for s in settings.shapes if s.is_saved)
        layout.label(text=f"{saved_n} / {len(settings.shapes)} shapes saved")
        layout.operator("arkit.apply_all", icon='CHECKMARK')
        layout.operator("arkit.init_shape_list", text="Clear Saved Poses", icon='FILE_REFRESH')


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    ARKitBoneDelta,
    ARKitShapeDef,
    ARKitBonePair,
    ARKitRecorderSettings,
    ARKIT_OT_hint_label,
    ARKIT_OT_init_list,
    ARKIT_OT_save_pose,
    ARKIT_OT_refresh_bone_pairs,
    ARKIT_OT_mirror_shape,
    ARKIT_OT_preview_pose,
    ARKIT_OT_reset_pose,
    ARKIT_OT_apply_all,
    ARKIT_OT_export_json,
    ARKIT_OT_import_json,
    ARKIT_UL_shapes,
    ARKIT_PT_panel,
)


def _deferred_init():
    """Runs via a timer, outside any restricted context, so it's safe to
    write scene data here even though it isn't safe in draw() or directly
    inside register()/load_post."""
    for scene in bpy.data.scenes:
        settings = scene.arkit_recorder
        if not settings.shapes:
            populate_default_shapes(settings)
    return None  # don't repeat the timer


def _request_deferred_populate():
    if not bpy.app.timers.is_registered(_deferred_init):
        bpy.app.timers.register(_deferred_init, first_interval=0.1)


@persistent
def arkit_load_post_handler(dummy):
    # New/opened files may have a scene with an empty shape list.
    _request_deferred_populate()


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.arkit_recorder = PointerProperty(type=ARKitRecorderSettings)

    if arkit_load_post_handler not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(arkit_load_post_handler)

    # Cover the "addon just enabled mid-session" case too.
    _request_deferred_populate()


def unregister():
    if arkit_load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(arkit_load_post_handler)
    if bpy.app.timers.is_registered(_deferred_init):
        bpy.app.timers.unregister(_deferred_init)
    stop_preview_timer()
    clear_preview_collections()
    del bpy.types.Scene.arkit_recorder
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()