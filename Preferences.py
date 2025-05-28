import bpy
from bpy.props import (
    BoolProperty,
    FloatProperty,
)
from bpy.types import AddonPreferences


class RightMouseNavigationPreferences(AddonPreferences):
    bl_idname = __package__

    time: FloatProperty(
        name="Time Threshold",
        description="How long to hold right mouse before auto-activating walk mode (also determines menu timing on release)",
        default=0.1,
        min=0.01,
        max=1,
    )

    return_to_ortho_on_exit: BoolProperty(
        name="Return to Orthographic on Exit",
        description="After exiting navigation, this determines if the Viewport "
        "returns to Orthographic view (if checked) or remains in Perspective view (if unchecked)",
        default=True,
    )

    disable_camera_navigation: BoolProperty(
        name="Disable Navigation for Camera View",
        description="Enable if you only want to navigate your scene, and not affect Camera Transform",
        default=False,
    )

    walk_mode_focal_length_enable: BoolProperty(
        name="Switch Focal Length while Active",
        description="Enable to switch focal length during walk/fly mode",
        default=True,
    )

    walk_mode_focal_length: FloatProperty(
        name="Focal Length",
        description="Focal length for the viewport during walk/fly mode.",
        default=30.0,
        min=0.0,
        max=250.0,
        subtype='UNSIGNED',
        unit='CAMERA'
    )

    walk_mode_transition_duration: FloatProperty(
        name="Transition Duration",
        description="Duration of focal length transition in seconds (0 = instant)",
        default=0.1,
        min=0.0,  # Allow 0 to disable transitions
        max=1.0,
        step=1,
        precision=2,
        subtype='TIME'
    )

    def draw(self, context):
        layout = self.layout

        row1 = layout.row() # First row for Timing
        box_timing = row1.box()
        box_timing.label(text="Menu / Movement", icon="DRIVER_DISTANCE") # Restored original label
        box_timing.prop(self, "time")
        # disable_camera_navigation is removed from this box

        # The View box that was previously here is moved to the next row.

        row2 = layout.row() # Second row for Camera and View settings

        box_camera = row2.box() # Camera settings, in the old "Cursor" slot
        box_camera.label(text="Camera", icon="CAMERA_DATA")
        box_camera.prop(self, "disable_camera_navigation")

        box_view = row2.box() # View settings, next to Camera settings
        box_view.label(text="View", icon="VIEW3D")
        box_view.prop(self, "return_to_ortho_on_exit")
        box_view.prop(self, "walk_mode_focal_length_enable")
        if self.walk_mode_focal_length_enable:
            box_view.prop(self, "walk_mode_focal_length")
            box_view.prop(self, "walk_mode_transition_duration")

        # Keymap Customization
        import rna_keymap_ui

        nav_names = [
            "FORWARD",
            "FORWARD_STOP",
            "BACKWARD",
            "BACKWARD_STOP",
            "LEFT",
            "LEFT_STOP",
            "RIGHT",
            "RIGHT_STOP",
            "UP",
            "UP_STOP",
            "DOWN",
            "DOWN_STOP",
            "LOCAL_UP",
            "LOCAL_UP_STOP",
            "LOCAL_DOWN",
            "LOCAL_DOWN_STOP",
        ]

        wm = bpy.context.window_manager
        active_kc = wm.keyconfigs.active

        addon_keymaps = []

        walk_km = active_kc.keymaps["View3D Walk Modal"]

        for key in walk_km.keymap_items:
            addon_keymaps.append((walk_km, key))

        header, panel = layout.panel(idname="keymap", default_closed=True)
        header.label(text="Navigation Keymap")

        wm = bpy.context.window_manager
        kc = wm.keyconfigs.user
        old_km_name = ""
        get_kmi_l = []
        for km_add, kmi_add in addon_keymaps:
            for km_con in kc.keymaps:
                if km_add.name == km_con.name:
                    km = km_con
                    break

            for kmi_con in km.keymap_items:
                if kmi_add.idname == kmi_con.idname:
                    if kmi_add.name == kmi_con.name and kmi_con.propvalue in nav_names:
                        get_kmi_l.append((km, kmi_con))

        get_kmi_l = sorted(set(get_kmi_l), key=get_kmi_l.index)

        if panel:
            col = panel.column(align=True)
            for km, kmi in get_kmi_l:
                if not km.name == old_km_name:
                    col.label(text=str(km.name), icon="DOT")
                col.context_pointer_set("keymap", km)
                rna_keymap_ui.draw_kmi([], kc, km, kmi, col, 0)
                col.separator()
                old_km_name = km.name
