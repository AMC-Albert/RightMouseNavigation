import bpy
from bpy.props import (
    BoolProperty,
    FloatProperty,
)
from bpy.types import AddonPreferences


def update_node_keymap(self, context):
    print(f"[NODE KEYMAP DEBUG] update_node_keymap called with enable_for_node_editors: {self.enable_for_node_editors}")
    
    wm = context.window_manager
    
    # Update our addon's Node Editor keymap item
    addon_kc = wm.keyconfigs.addon
    if addon_kc and "Node Editor" in addon_kc.keymaps:
        km = addon_kc.keymaps["Node Editor"]
        for kmi in km.keymap_items:
            if kmi.idname == "rmn.right_mouse_navigation" and kmi.type == "RIGHTMOUSE":
                kmi.active = self.enable_for_node_editors
                print(f"[NODE KEYMAP DEBUG] Set RMN Node Editor keymap to: {kmi.active}")
                break
        else:
            print(f"[NODE KEYMAP DEBUG] RMN keymap item not found in addon keyconfig")
    else:
        print(f"[NODE KEYMAP DEBUG] Node Editor keymap not found in addon keyconfig")
    
    # Update Blender's default Node Editor RMB menu
    active_kc = wm.keyconfigs.active
    if active_kc and "Node Editor" in active_kc.keymaps:
        km = active_kc.keymaps["Node Editor"]
        for kmi in km.keymap_items:
            if kmi.idname == "wm.call_menu" and kmi.type == "RIGHTMOUSE":
                kmi.active = not self.enable_for_node_editors
                print(f"[NODE KEYMAP DEBUG] Set Blender default Node Editor menu to: {kmi.active}")
                break
        else:
            print(f"[NODE KEYMAP DEBUG] Blender default menu keymap not found")
    else:
        print(f"[NODE KEYMAP DEBUG] Node Editor keymap not found in active keyconfig")

    # Refresh keymaps
    wm.keyconfigs.update()


class RightMouseNavigationPreferences(AddonPreferences):
    bl_idname = __package__

    time: FloatProperty(
        name="Time Threshold",
        description="How long to hold right mouse before auto-activating walk mode (also determines menu timing on release)",
        default=0.1,
        min=0.01,
        max=1,
    )

    reset_cursor_on_exit: BoolProperty(
        name="Reset Cursor on Exit",
        description="After exiting navigation, this determines if the cursor stays "
        "where RMB was clicked (if unchecked) or resets to the center (if checked)",
        default=False,
    )

    return_to_ortho_on_exit: BoolProperty(
        name="Return to Orthographic on Exit",
        description="After exiting navigation, this determines if the Viewport "
        "returns to Orthographic view (if checked) or remains in Perspective view (if unchecked)",
        default=True,
    )

    enable_for_node_editors: BoolProperty(
        name="Enable for Node Editors",
        description="Right Mouse will pan the view / open the Node Add/Search Menu",
        default=False,
        update=update_node_keymap,
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

        row = layout.row()
        box = row.box()
        box.label(text="Menu / Movement", icon="DRIVER_DISTANCE")
        box.prop(self, "time")
        box = row.box()
        box.label(text="Node Editor", icon="NODETREE")
        box.prop(self, "enable_for_node_editors")

        row = layout.row()
        box = row.box()
        box.label(text="Cursor", icon="ORIENTATION_CURSOR")
        box.prop(self, "reset_cursor_on_exit")
        box = row.box()
        box.label(text="View", icon="VIEW3D")
        box.prop(self, "return_to_ortho_on_exit")
        box.prop(self, "walk_mode_focal_length_enable")  # New toggle above the slider
        if self.walk_mode_focal_length_enable:
            box.prop(self, "walk_mode_focal_length") # Only show slider if enabled
            box.prop(self, "walk_mode_transition_duration") # Show transition duration setting

        row = layout.row()
        box = row.box()
        box.label(text="Camera", icon="CAMERA_DATA")
        box.prop(self, "disable_camera_navigation")

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
