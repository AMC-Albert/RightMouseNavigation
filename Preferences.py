import bpy
from bpy.props import (
    BoolProperty,
    FloatProperty,
    StringProperty,
    EnumProperty,
)
from bpy.types import AddonPreferences, Operator  # Added Operator
import rna_keymap_ui  # Ensure it's imported for draw_kmi

# Moved from __init__.py for use in RefreshKeymapsOperator and draw()
RMN_OPERATOR_IDNAME = "rmn.right_mouse_navigation"
RMN_CUSTOM_KMI_ID = "rmn_custom_activation_kmi"


# Update function for keymap-affecting preferences
# This function is called by properties and the refresh operator.
# It expects 'self_prefs' to be an instance of RightMouseNavigationPreferences
def _update_keymaps_logic(self_prefs, context):
    """Requests keymap update when activation preferences change."""
    # print(f"[{__package__}] _update_keymaps_logic called by: {self_prefs}")
    try:
        from . import unregister_keymaps, register_keymaps
        # print(f"[{__package__}] Pref update: Triggering keymap reregistration.")
        unregister_keymaps(context)  # Pass context
        register_keymaps(context)  # Pass context
        # print(f"[{__package__}] Keymaps reregistered.")
    except ImportError:
        print(
            f"[{__package__}] Info: Keymap update skipped, registration functions not yet available (ImportError)."
        )
    except Exception as e:
        print(f"[{__package__}] Error during keymap reregistration: {e}")


class RefreshKeymapsOperator(Operator):
    """Operator to manually refresh keymaps based on current preferences."""

    bl_idname = "rmn.refresh_keymaps"
    bl_label = "Apply Custom Key and Refresh All Keymaps"
    bl_description = "Applies any changes to the custom activation key and re-registers all addon keymaps according to current settings. Use this after modifying the custom key with the editor below."

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        _update_keymaps_logic(prefs, context)
        self.report({'INFO'}, "Keymaps refreshed.")
        return {'FINISHED'}


class RightMouseNavigationPreferences(AddonPreferences):
    bl_idname = __package__

    # The update callback for EnumProperty needs self (prefs instance) and context
    def _enum_update_callback(self, context):
        _update_keymaps_logic(self, context)

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

    enable_camera_navigation: BoolProperty(
        name="Enable Navigation in Camera View",
        description="Enable to allow navigation while in camera view. If disabled, navigation will not affect the camera's transform or view.",
        default=True,
    )

    camera_nav_only_if_locked: BoolProperty(
        name="Only when Camera is Locked to View",
        description="If enabled, navigation in camera view is only active when Blender's 'Lock Camera to View' is also active.",
        default=True,
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

    # New Activation Preferences
    activation_method: EnumProperty(
        name="Activation Method",
        description="Choose how to activate navigation",
        items=[
            ('RMB', "Right Mouse", "Standard timed activation (allows context menu on short press)"),
            ('MMB', "Middle Mouse", "Instant activation with Middle Mouse Button (no context menu)"),
            ('KEY', "Keyboard Key", "Instant activation with a specified keyboard key (no context menu, editable below)")
        ],
        default='RMB',
        update=_enum_update_callback  # Use the class method as callback
    )

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager  # For keymap access

        # Activation Settings Box
        box_activation = layout.box()
        box_activation.label(text="Activation Settings", icon="KEYINGSET")
        box_activation.prop(self, "activation_method")

        if self.activation_method == 'KEY':
            box_activation.label(text="Custom Activation Key (Editable):")

            addon_kc = wm.keyconfigs.addon
            # Ensure we are looking in the correct keymap where the item is registered.
            # register_keymaps places it in addon_kc.keymaps.new(name="3D View", space_type="VIEW_3D")
            km_3d_view_addon = None
            for km in addon_kc.keymaps: # Iterate through addon keyconfigs
                if km.name == "3D View" and km.space_type == "VIEW_3D":
                    km_3d_view_addon = km
                    break
            
            custom_kmi_to_draw = None
            if km_3d_view_addon:
                for kmi in km_3d_view_addon.keymap_items:
                    # Check .name for the ID we assigned
                    if kmi.idname == RMN_OPERATOR_IDNAME and kmi.name == RMN_CUSTOM_KMI_ID:
                        custom_kmi_to_draw = kmi
                        break
            
            if custom_kmi_to_draw:
                col = box_activation.column()
                col.context_pointer_set("keymap", km_3d_view_addon) 
                rna_keymap_ui.draw_kmi([], addon_kc, km_3d_view_addon, custom_kmi_to_draw, col, 0)
                box_activation.operator(RefreshKeymapsOperator.bl_idname, icon='FILE_REFRESH')
            else:
                box_activation.label(text="Custom key item not found. Defaulting or select 'KEY' again.", icon='ERROR')
                box_activation.operator(RefreshKeymapsOperator.bl_idname, text="Initialize/Refresh Custom Key", icon='FILE_REFRESH')

        # Time threshold only relevant for RMB activation
        row_time_outer = layout.row()
        box_timing = row_time_outer.box()
        box_timing.label(text="Menu / Movement Delay (RMB Only)", icon="DRIVER_DISTANCE")
        row_time_prop = box_timing.row()
        row_time_prop.prop(self, "time")
        row_time_prop.enabled = self.activation_method == 'RMB'
        if self.activation_method != 'RMB':
            box_timing.label(text="Delay not applicable for current activation method.")

        row2 = layout.row()  # Second row for Camera and View settings

        box_camera = row2.box()
        box_camera.label(text="Camera Navigation", icon="CAMERA_DATA")
        box_camera.prop(self, "enable_camera_navigation")
        if self.enable_camera_navigation:
            box_camera.prop(self, "camera_nav_only_if_locked")

        box_view = row2.box()
        box_view.label(text="View", icon="VIEW3D")
        box_view.prop(self, "return_to_ortho_on_exit")
        box_view.prop(self, "walk_mode_focal_length_enable")
        if self.walk_mode_focal_length_enable:
            box_view.prop(self, "walk_mode_focal_length")
            box_view.prop(self, "walk_mode_transition_duration")

        # Informational labels based on activation method (moved from old activation box)
        if self.activation_method == 'RMB':
            layout.label(text="Hint: With Right Mouse, a quick click opens the context menu.")
        elif self.activation_method == 'MMB':
            layout.label(text="Hint: Middle Mouse activates navigation instantly.")
        elif self.activation_method == 'KEY':
            # layout.label(text=f"Hint: Custom key (see editor above) activates navigation instantly.")
            # The f-string here might be problematic if custom_activation_key is removed.
            # Better to have a generic message or retrieve from the KMI if possible, but that's complex for a simple label.
            layout.label(text="Hint: Custom key (configured above) activates navigation instantly.")

        # Keymap Customization (for Walk Modal keys)
        # import rna_keymap_ui # Already imported at the top

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
