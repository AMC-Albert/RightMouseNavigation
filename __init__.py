from .Preferences import RightMouseNavigationPreferences, RefreshKeymapsOperator
from .RightMouseNavigation import RMN_OT_right_mouse_navigation
import bpy

# Constants for Keymap Management (also used in Preferences.py)
RMN_OPERATOR_IDNAME = "rmn.right_mouse_navigation"
RMN_DEFAULT_KMI_ID = "rmn_default_activation_kmi" # For RMB default
RMN_CUSTOM_KMI_ID = "rmn_custom_activation_kmi"    # For MMB or KEY custom

addon_keymaps = []  # Stores (keymap, keymap_item) tuples for cleanup

# Store references to original keymap items that are modified by this addon
original_keymap_states = {}

def get_prefs(context):
    return context.preferences.addons[__package__].preferences

def _disable_default_rmb_menus(context):
    """Disables default Right Mouse Button menus/actions in various modes."""
    # print("[_disable_default_rmb_menus] Disabling default RMB actions.")
    wm = context.window_manager
    active_kc = wm.keyconfigs.active

    modes_to_check = {
        "Object Mode": "wm.call_menu",
        "Mesh": "wm.call_menu",
        "Curve": "wm.call_menu",
        "Armature": "wm.call_menu",
        "Metaball": "wm.call_menu",
        "Lattice": "wm.call_menu",
        "Font": "wm.call_menu",
        "Pose": "wm.call_menu",
        "Vertex Paint": "wm.call_panel",
        "Weight Paint": "wm.call_panel",
        "Image Paint": "wm.call_panel",
        "Sculpt": "wm.call_panel",
    }

    for mode_name, idname_to_check in modes_to_check.items():
        if mode_name in active_kc.keymaps:
            km = active_kc.keymaps[mode_name]
            for kmi in km.keymap_items:
                if kmi.idname == idname_to_check and kmi.type == "RIGHTMOUSE" and kmi.value == "PRESS":
                    if kmi.active:
                        original_keymap_states[(km.name, kmi.idname, kmi.type, kmi.value)] = True
                        kmi.active = False
                        # print(f"  Disabled: {km.name} -> {kmi.idname}")
                    else:
                        # If already inactive, store it as such so we don't incorrectly reactivate it
                        original_keymap_states[(km.name, kmi.idname, kmi.type, kmi.value)] = False 

def _restore_default_rmb_menus(context):
    """Restores default Right Mouse Button menus/actions in various modes."""
    # print("[_restore_default_rmb_menus] Restoring default RMB actions.")
    wm = context.window_manager
    active_kc = wm.keyconfigs.active

    for (km_name, kmi_idname, kmi_type, kmi_value), was_active in original_keymap_states.items():
        if km_name in active_kc.keymaps:
            km = active_kc.keymaps[km_name]
            for kmi in km.keymap_items:
                if kmi.idname == kmi_idname and kmi.type == kmi_type and kmi.value == kmi_value:
                    if was_active:
                        kmi.active = True
                        # print(f"  Restored: {km.name} -> {kmi.idname}")
                    break # Found the kmi, no need to continue loop for this entry
    original_keymap_states.clear()

def _modify_walk_modal_keymaps(context, register_phase):
    """Modifies the View3D Walk Modal keymap."""
    # print(f"[_modify_walk_modal_keymaps] Register phase: {register_phase}")
    wm = context.window_manager
    active_kc = wm.keyconfigs.active
    walk_km_name = "View3D Walk Modal"

    if walk_km_name in active_kc.keymaps:
        walk_km = active_kc.keymaps[walk_km_name]
        for kmi in walk_km.keymap_items:
            key_id = (walk_km.name, kmi.idname, kmi.propvalue, kmi.type, kmi.value)
            if register_phase:
                # Store original state before modifying
                original_keymap_states[key_id] = (kmi.active, kmi.type, kmi.value)
                
                if kmi.propvalue == "CANCEL" and kmi.type == "RIGHTMOUSE":
                    kmi.active = False
                    # print(f"  Walk Modal: Disabled CANCEL on RMB")
                elif kmi.propvalue == "CONFIRM" and kmi.type == "LEFTMOUSE":
                    kmi.type = "RIGHTMOUSE"
                    kmi.value = "RELEASE"
                    # print(f"  Walk Modal: Changed CONFIRM from LMB to RMB Release")
            else: # Unregister phase
                if key_id in original_keymap_states:
                    original_active, original_type, original_value = original_keymap_states.pop(key_id)
                    kmi.active = original_active
                    kmi.type = original_type
                    kmi.value = original_value
                    # print(f"  Walk Modal: Restored {kmi.propvalue} to original state")


def register_keymaps(context=None):
    """Registers all keymaps for the addon based on preferences."""
    if context is None:
        context = bpy.context
    prefs = get_prefs(context)
    wm = context.window_manager
    addon_kc = wm.keyconfigs.addon

    # Ensure existing keymaps from this addon are cleared before re-registering
    # This is important because unregister_keymaps might not have run if prefs changed without full unregister.
    _clear_addon_keymaps(addon_kc) 

    km_3d_view = addon_kc.keymaps.new(name="3D View", space_type="VIEW_3D")

    if prefs.activation_method == 'RMB':
        # Pass RMN_DEFAULT_KMI_ID to the name parameter during creation
        kmi = km_3d_view.keymap_items.new(RMN_OPERATOR_IDNAME, "RIGHTMOUSE", "PRESS", name=RMN_DEFAULT_KMI_ID)
        addon_keymaps.append((km_3d_view, kmi))
        _disable_default_rmb_menus(context)
        _modify_walk_modal_keymaps(context, register_phase=True)
        # print(f"  Registered RMB activation keymap.")

    elif prefs.activation_method == 'MMB':
        # Pass RMN_CUSTOM_KMI_ID to the name parameter during creation
        kmi = km_3d_view.keymap_items.new(RMN_OPERATOR_IDNAME, "MIDDLEMOUSE", "PRESS", name=RMN_CUSTOM_KMI_ID)
        addon_keymaps.append((km_3d_view, kmi))
        # print(f"  Registered MMB activation keymap.")
        # No need to disable RMB menus or alter walk modal for MMB usually

    elif prefs.activation_method == 'KEY':
        # For 'KEY', we create a placeholder KMI. The user edits it via Preferences UI.
        # The RMN_CUSTOM_KMI_ID is crucial here.
        # Check if a KMI with this ID already exists from a previous registration or user edit.
        existing_kmi = None
        for item in km_3d_view.keymap_items:
            if item.idname == RMN_OPERATOR_IDNAME and item.name == RMN_CUSTOM_KMI_ID: # Check .name
                existing_kmi = item
                break
        
        if existing_kmi:
            # If it exists, ensure it's active and re-add to addon_keymaps for tracking.
            # Its properties (type, value, etc.) are managed by the user via draw_kmi.
            existing_kmi.active = True 
            addon_keymaps.append((km_3d_view, existing_kmi))
            # print(f"  Re-activated existing custom key: {existing_kmi.type}")
        else:
            # If it doesn't exist, create a new one with a default (e.g., 'F' key)
            # The user can then change this in preferences.
            kmi = km_3d_view.keymap_items.new(RMN_OPERATOR_IDNAME, 'F', 'PRESS', name=RMN_CUSTOM_KMI_ID)
            addon_keymaps.append((km_3d_view, kmi))
            # print(f"  Registered new custom key (default F) with ID: {RMN_CUSTOM_KMI_ID}")

def _clear_addon_keymaps(addon_kc):
    """Helper to remove all keymap items previously added by this addon."""
    names_to_remove_map = {}
    for km, kmi in addon_keymaps:
        if km.name not in names_to_remove_map:
            names_to_remove_map[km.name] = []
        names_to_remove_map[km.name].append(kmi.name) # Store kmi.name

    for km_name, kmi_names in names_to_remove_map.items():
        if km_name in addon_kc.keymaps:
            km_target = addon_kc.keymaps[km_name]
            for kmi_name_to_remove in kmi_names:
                for i in range(len(km_target.keymap_items) - 1, -1, -1):
                    kmi_iter = km_target.keymap_items[i]
                    if kmi_iter.idname == RMN_OPERATOR_IDNAME and kmi_iter.name == kmi_name_to_remove: # Check .name
                        km_target.keymap_items.remove(kmi_iter)
                        break 
    addon_keymaps.clear()

def unregister_keymaps(context=None):
    """Unregisters all keymaps for the addon."""
    if context is None:
        context = bpy.context
    prefs = get_prefs(context)
    wm = context.window_manager
    addon_kc = wm.keyconfigs.addon

    _clear_addon_keymaps(addon_kc)

    # Only restore/modify if RMB was the method, as other methods don't change these.
    # Check current prefs, but ideally, this state should be stored from when they were disabled.
    # The new original_keymap_states handles this better.
    _restore_default_rmb_menus(context)
    _modify_walk_modal_keymaps(context, register_phase=False)
    # print(f"  Keymaps unregistered and defaults restored if necessary.")

def register():
    if not bpy.app.background:
        bpy.utils.register_class(RightMouseNavigationPreferences)
        bpy.utils.register_class(RMN_OT_right_mouse_navigation)
        bpy.utils.register_class(RefreshKeymapsOperator) # Register the operator
        register_keymaps() # Initial keymap registration

def unregister():
    if not bpy.app.background:
        unregister_keymaps() # Unregister keymaps first
        bpy.utils.unregister_class(RMN_OT_right_mouse_navigation)
        bpy.utils.unregister_class(RightMouseNavigationPreferences)
        bpy.utils.unregister_class(RefreshKeymapsOperator) # Unregister the operator

if __name__ == "__main__":
    register()
