import bpy
from bpy.types import Operator
from .FocalLengthManager import FocalLengthManager


class RMN_OT_right_mouse_navigation(Operator):
    """Handles right-click initiated navigation or context menu display."""

    bl_idname = "rmn.right_mouse_navigation"
    bl_label = "Right Mouse Navigation"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _count = 0.0 # Using float for time accumulation
    _finished = False
    _callMenu = False
    _ortho = False # Tracks if the view was originally orthographic
    _back_to_ortho = False # Flag to restore orthographic view on exit
    _focal_manager = None
    _waiting_for_input = False
    _navigation_started = False
    _initial_event = None # Stores the initial mouse event from invoke

    NAV_KEYS = {
        'W', 'A', 'S', 'D',  # Standard movement
        'Q', 'E',          # Up/Down (often Z-axis)
        'SPACE', 'LEFT_SHIFT', # Alternative Up/Down or modifiers
        'UP_ARROW', 'DOWN_ARROW', 'LEFT_ARROW', 'RIGHT_ARROW' # Arrow key movement
    }

    menu_by_mode = {
        "OBJECT": "VIEW3D_MT_object_context_menu",
        "EDIT_MESH": "VIEW3D_MT_edit_mesh_context_menu",
        "EDIT_SURFACE": "VIEW3D_MT_edit_surface",
        "EDIT_TEXT": "VIEW3D_MT_edit_font_context_menu",
        "EDIT_ARMATURE": "VIEW3D_MT_edit_armature",
        "EDIT_CURVE": "VIEW3D_MT_edit_curve_context_menu",
        "EDIT_METABALL": "VIEW3D_MT_edit_metaball_context_menu",
        "EDIT_LATTICE": "VIEW3D_MT_edit_lattice_context_menu",
        "POSE": "VIEW3D_MT_pose_context_menu",
        "PAINT_VERTEX": "VIEW3D_PT_paint_vertex_context_menu",
        "PAINT_WEIGHT": "VIEW3D_PT_paint_weight_context_menu",
        "PAINT_TEXTURE": "VIEW3D_PT_paint_texture_context_menu",
        "SCULPT": "VIEW3D_PT_sculpt_context_menu",
    }

    def _perform_final_cleanup(self, context):
        """Performs all necessary cleanup actions when the operator finishes or is cancelled."""
        addon_prefs = context.preferences.addons[__package__].preferences

        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

        if self._callMenu:
            self.callMenu(context)

        if self._back_to_ortho:
            bpy.ops.view3d.view_persportho()

        if self._focal_manager:
            self._focal_manager.cleanup(context, addon_prefs)

    def modal(self, context, event):
        """Handles events while the operator is in a modal state."""
        if context.space_data is None:
            # print(f"[RMN DEBUG] context.space_data is None in modal. Event: {event.type}. Finishing operator.")
            if self._timer:
                try:
                    context.window_manager.event_timer_remove(self._timer)
                except Exception: # pylint: disable=broad-except
                    # print(f"[RMN DEBUG] Error removing main timer: {e}")
                    pass
                self._timer = None
            return {'CANCELLED'}

        addon_prefs = context.preferences.addons[__package__].preferences
        space_type = context.space_data.type
        # General event logging can be enabled here if needed for deep debugging
        # print(f"[RMN] Modal Event: {event.type} ({event.value}), Count: {self._count:.2f}, Nav: {self._navigation_started}, Wait: {self._waiting_for_input}, Fin: {self._finished}")

        # --- 3D Viewport Specific Logic ---
        if space_type == "VIEW_3D":
            if self._waiting_for_input:
                if event.type in self.NAV_KEYS and event.value == 'PRESS':
                    if self._start_navigation(context):
                        return {"PASS_THROUGH"}
                    self._perform_final_cleanup(context)
                    return {"CANCELLED"}

                if event.type == "RIGHTMOUSE" and event.value == "RELEASE":
                    # context.window.cursor_modal_restore() # Cursor restoration is now implicit or handled by Blender
                    if self._count < addon_prefs.time:
                        self._callMenu = True
                    self.cancel(context) # Triggers cleanup via _finished flag
                    self._finished = True
                    return {"PASS_THROUGH"}

            if self._navigation_started and not self._finished:
                # If walk mode is active, any event other than Timer or MouseMove
                # indicates walk mode has ended.
                if event.type not in {"TIMER", "MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
                    if event.type == "RIGHTMOUSE" and event.value == "RELEASE":
                        # context.window.cursor_modal_restore() # Cursor restoration is now implicit or handled by Blender
                        # Check if menu should be called, even if navigation was briefly active
                        if self._count < addon_prefs.time:
                            self._callMenu = True
                    self.cancel(context)
                    self._finished = True
                    return {"PASS_THROUGH"}
        # --- End 3D Viewport Specific Logic ---

        if event.type == "TIMER":
            if space_type == "VIEW_3D": # Timer logic primarily for 3D view
                auto_activation_threshold = addon_prefs.time
                if (self._waiting_for_input and
                        not self._navigation_started and
                        auto_activation_threshold > 0 and
                        self._count >= auto_activation_threshold):
                    if self._start_navigation(context):
                        return {"RUNNING_MODAL"} # Stay modal
                    self._perform_final_cleanup(context)
                    return {"CANCELLED"}

                if self._focal_manager:
                    was_exit_transition = self._focal_manager.is_exit_transition
                    transition_completed = self._focal_manager.update_transition(context)
                    if transition_completed and self._finished and was_exit_transition:
                        self._perform_final_cleanup(context)
                        return {"CANCELLED"}

            if not self._finished:
                self._count += 0.02 # Timer interval
            return {"PASS_THROUGH"}

        if self._finished:
            if self._focal_manager and self._focal_manager.is_transitioning:
                return {"PASS_THROUGH"} # Let transition complete

            if self._focal_manager and self._focal_manager.start_exit_transition(context, addon_prefs):
                return {"PASS_THROUGH"} # Start exit transition if needed

            self._perform_final_cleanup(context)
            return {"CANCELLED"}

        return {"PASS_THROUGH"}

    def callMenu(self, context):
        """Calls the appropriate context menu based on the current mode and selection."""
        select_mouse = context.window_manager.keyconfigs.active.preferences.select_mouse
        space_type = context.space_data.type

        if space_type == "VIEW_3D":
            if select_mouse == "LEFT":
                try:
                    bpy.ops.wm.call_menu(name=self.menu_by_mode[context.mode])
                except (RuntimeError, KeyError): # Catch if menu name is wrong or mode not in dict
                    # Fallback or error reporting can be added here
                    # print(f"[RMN] Error calling menu for mode: {context.mode}")
                    pass # Silently fail for now
            else: # Right-click select
                bpy.ops.view3d.select("INVOKE_DEFAULT")

    def invoke(self, context, event):
        """Initializes the operator state when it's called."""
        # print(f"[RMN INVOKE] Called in {context.space_data.type if context.space_data else 'Unknown Space'}")
        self._count = 0.0
        self._finished = False
        self._callMenu = False
        self._ortho = False
        self._back_to_ortho = False
        self._waiting_for_input = True
        self._navigation_started = False
        self._focal_manager = FocalLengthManager()
        self._initial_event = event

        self.view_x = event.mouse_x
        self.view_y = event.mouse_y
        return self.execute(context)

    def execute(self, context):
        """Sets up the modal timer if in the 3D View."""
        space_type = context.space_data.type if context.space_data else None
        # print(f"[RMN EXECUTE] space_type: {space_type}")

        if space_type == "VIEW_3D":
            wm = context.window_manager
            self._timer = wm.event_timer_add(0.02, window=context.window) # 50 FPS timer
            wm.modal_handler_add(self)
            # print(f"[RMN EXECUTE] 3D View timer created: {self._timer}")
            return {"RUNNING_MODAL"}

        # print(f"[RMN EXECUTE] No modal conditions met for {space_type}, returning FINISHED")
        return {"FINISHED"} # Default for non-3D view contexts

    def _start_navigation(self, context):
        """Attempts to start Blender's walk/fly navigation."""
        addon_prefs = context.preferences.addons[__package__].preferences
        enable_camera_nav = addon_prefs.enable_camera_navigation
        only_if_locked = addon_prefs.camera_nav_only_if_locked

        if not context.space_data or not context.space_data.region_3d:
            return False # Cannot navigate without 3D region data

        view_perspective_type = context.space_data.region_3d.view_perspective

        if view_perspective_type == "CAMERA":
            if not enable_camera_nav:
                # Navigation in camera view is explicitly disabled.
                # print(\"[RMN] Navigation in Camera view disabled by user preference (enable_camera_navigation is False).\")
                return False
            
            # At this point, enable_camera_nav is True.
            # Now check the 'Only when Camera is Locked to View' sub-toggle.
            if only_if_locked:
                if not context.space_data.lock_camera:
                    # Sub-toggle is on, but camera is not locked to view.
                    # print(\"[RMN] Navigation in Camera view disabled: 'Only when Camera is Locked to View' is ON, but camera is not locked.\")
                    return False
                # else: Navigation allowed (sub-toggle on, camera locked)
            # else: Navigation allowed (sub-toggle off, lock_camera state doesn't matter for this check)

        try:
            if self._focal_manager:
                self._focal_manager.start_entry_transition(context, addon_prefs)

            bpy.ops.view3d.walk('INVOKE_DEFAULT')
            self._navigation_started = True
            self._waiting_for_input = False

            if not context.region_data.is_perspective: # Check if current view is orthographic
                self._ortho = True # Mark that we started in ortho
                if addon_prefs.return_to_ortho_on_exit:
                    self._back_to_ortho = True
            else:
                self._ortho = False
                self._back_to_ortho = False


            return True
        except RuntimeError:
            # This can happen if, for example, trying to navigate a camera with constraints
            # print(f"[RMN DEBUG] RuntimeError in _start_navigation: {e}")
            self.report({"WARNING"}, "Navigation failed. Object might have constraints or view is locked.")
            return False
        # except Exception as e: # Catch any other unexpected error
            # print(f"[RMN ERROR] Unexpected error in _start_navigation: {e}")
            # self.report({"ERROR"}, "An unexpected error occurred during navigation startup.")
            # return False


    def cancel(self, context):
        """Handles operator cancellation, including focal length restoration for interrupted entry."""
        # This method is primarily called when _finished is set to True,
        # or when Blender cancels the operator (e.g., ESC key in some states).
        # The actual timer removal and other cleanup often happens in _perform_final_cleanup
        # once the _finished flag is processed in the modal loop.

        if context.space_data and context.space_data.type == "VIEW_3D" and self._focal_manager:
            addon_prefs = context.preferences.addons[__package__].preferences
            # If an entry transition was active and interrupted, force restore.
            if self._focal_manager.is_transitioning and not self._focal_manager.is_exit_transition:
                self._focal_manager.force_restore_original(context, addon_prefs)

        # Ensure cursor is restored if modal was active - No longer explicitly managed here
        # try:
        #     context.window.cursor_modal_restore()
        # except Exception: # pylint: disable=broad-except
        #     pass # May not have been set or already restored

        # DO NOT remove the timer here.
        # The _perform_final_cleanup method is responsible for removing the timer
        # after all modal operations, including exit transitions, are complete.
        # Prematurely removing it here would break the exit transition.