import bpy
from bpy.types import Operator
from .FocalLengthManager import FocalLengthManager


class RMN_OT_right_mouse_navigation(Operator):
    """Timer that decides whether to display a menu after Right Click"""

    bl_idname = "rmn.right_mouse_navigation"
    bl_label = "Right Mouse Navigation"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _count = 0
    MOUSE_RIGHTUP = 0x0010
    _finished = False
    _callMenu = False
    _ortho = False
    _back_to_ortho = False
    _focal_manager = None
    _waiting_for_input = False  # New state for waiting
    _navigation_started = False  # Track if navigation has been activated

    NAV_KEYS = {
        'W', 'A', 'S', 'D',  # Movement
        'Q', 'E',  # Up/Down
        'SPACE', 'LEFT_SHIFT',  # Local up/down
        'UP_ARROW', 'DOWN_ARROW', 'LEFT_ARROW', 'RIGHT_ARROW'  # Arrow keys
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

    def _reset_cursor_action(self, context):
        area = context.area
        x = area.x
        y = area.y
        x += int(area.width / 2)
        y += int(area.height / 2)
        bpy.context.window.cursor_warp(x, y)

    def _perform_final_cleanup(self, context):
        addon_prefs = context.preferences.addons[__package__].preferences
        space_type = context.space_data.type

        # Remove timer if it hasn't been removed yet
        if self._timer:
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
            self._timer = None

        if self._callMenu:
            if addon_prefs.reset_cursor_on_exit and not space_type == "NODE_EDITOR":
                self._reset_cursor_action(context)
            self.callMenu(context)
        else:
            if addon_prefs.reset_cursor_on_exit:
                self._reset_cursor_action(context)

        if self._back_to_ortho:
            bpy.ops.view3d.view_persportho()

        # Use focal manager for cleanup
        if self._focal_manager:
            self._focal_manager.cleanup(context, addon_prefs)

    def modal(self, context, event):
        preferences = context.preferences
        addon_prefs = preferences.addons[__package__].preferences
        enable_nodes = addon_prefs.enable_for_node_editors

        space_type = context.space_data.type
        # print(f"[RMN DEBUG] Event: {event.type} ({event.value})") # General log if needed

        # Handle events for node editor FIRST - before general processing
        if space_type == "NODE_EDITOR" and enable_nodes:
            if event.type in {"RIGHTMOUSE"}:
                if event.value in {"RELEASE"}:
                    context.window.cursor_modal_restore()
                    
                    # Direct menu handling for node editor
                    if self._count < addon_prefs.time:
                        # Call menu immediately
                        self.callMenu(context)
                    
                    # Simple cleanup for node editor
                    wm = context.window_manager
                    if self._timer:
                        wm.event_timer_remove(self._timer)
                        self._timer = None
                    
                    # Reset cursor if needed
                    if addon_prefs.reset_cursor_on_exit:
                        self._reset_cursor_action(context)
                    
                    return {"FINISHED"}
            
            # For node editor, start pan after threshold time
            if event.type == "TIMER":
                if self._count >= addon_prefs.time and not self._navigation_started:
                    # Start panning mode after threshold
                    try:
                        bpy.ops.view2d.pan("INVOKE_DEFAULT")
                        self._navigation_started = True
                        # Remove timer once panning starts - no longer needed
                        wm = context.window_manager
                        if self._timer:
                            wm.event_timer_remove(self._timer)
                            self._timer = None
                        return {"PASS_THROUGH"}
                    except Exception as e:
                        print(f"[NODE DEBUG] Failed to start pan: {e}")
                
                # Only increment count if navigation hasn't started yet
                if not self._finished and not self._navigation_started:
                    self._count += 0.02
                    
                return {"PASS_THROUGH"}

            return {"PASS_THROUGH"}

        # Handle waiting state - looking for navigation input OR time threshold
        if self._waiting_for_input and space_type == "VIEW_3D":
            # Check for navigation key presses (immediate activation)
            if event.type in self.NAV_KEYS and event.value == 'PRESS':
                # User wants to navigate - start navigation mode immediately
                if self._start_navigation(context):
                    return {"PASS_THROUGH"}
                else:
                    self._perform_final_cleanup(context)
                    return {"CANCELLED"}
            
            # Check for right mouse release while waiting
            if event.type == "RIGHTMOUSE" and event.value == "RELEASE":
                context.window.cursor_modal_restore()
                if self._count < addon_prefs.time:
                    self._callMenu = True
                self.cancel(context)
                self._finished = True
                return {"PASS_THROUGH"}

        # When navigation is active, intercept ALL events to detect when walk mode ends
        if self._navigation_started and not self._finished:
            # Any event that reaches us while navigation is supposed to be active
            # means walk mode has ended (since walk mode would normally consume events)
            if event.type not in {"TIMER", "MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
                # Walk mode ended, trigger our cleanup
                if event.type == "RIGHTMOUSE" and event.value == "RELEASE":
                    context.window.cursor_modal_restore()
                    if self._count < addon_prefs.time:
                        self._callMenu = True
                
                self.cancel(context)
                self._finished = True
                return {"PASS_THROUGH"}

        # Always handle TIMER events
        if event.type == "TIMER" and space_type != "NODE_EDITOR":
            # Check if we should auto-activate walk mode based on time threshold
            # Use the same threshold as menu timing for consistency
            auto_activation_threshold = addon_prefs.time
            if (self._waiting_for_input and space_type == "VIEW_3D" and 
                not self._navigation_started and auto_activation_threshold > 0 and 
                self._count >= auto_activation_threshold):
                # Auto-activate walk mode after threshold time
                if self._start_navigation(context):
                    return {"RUNNING_MODAL"}
                else:
                    self._perform_final_cleanup(context)
                    return {"CANCELLED"}

            # Handle focal length transitions (both entry and exit)
            if self._focal_manager and space_type == "VIEW_3D":
                # Store the exit transition state before update (it gets cleared during update)
                was_exit_transition = self._focal_manager.is_exit_transition
                transition_completed = self._focal_manager.update_transition(context)
                
                # If exit transition completed and we're finished, clean up and exit
                if transition_completed and self._finished and was_exit_transition:
                    self._perform_final_cleanup(context)
                    return {"CANCELLED"}
            
            # Always increment count if not finished, regardless of menu threshold
            # Now incrementing by 0.02 seconds (50 FPS) for better responsiveness
            if not self._finished:
                self._count += 0.02
            
            # Always return PASS_THROUGH for TIMER events to ensure consistent processing
            return {"PASS_THROUGH"}

        # Handle the finished state after processing transitions
        if self._finished:
            # If a transition is currently running, let it continue
            if self._focal_manager and self._focal_manager.is_transitioning:
                return {"PASS_THROUGH"}
            
            # Check if an exit transition needs to be started
            # This should happen if we have an original lens stored, regardless of navigation state
            if (self._focal_manager and 
                self._focal_manager.start_exit_transition(context, addon_prefs)):
                return {"PASS_THROUGH"}
            else:
                # No transition needed or already completed
                self._perform_final_cleanup(context)
                return {"CANCELLED"}

        # If we're still waiting and not in any active state, pass through other events
        return {"PASS_THROUGH"}

    def callMenu(self, context):
        select_mouse = context.window_manager.keyconfigs.active.preferences.select_mouse
        space_type = context.space_data.type

        if select_mouse == "LEFT":
            if space_type == "NODE_EDITOR":
                node_tree = context.space_data.node_tree
                if node_tree:
                    if (
                        node_tree.nodes.active is not None
                        and node_tree.nodes.active.select
                    ):
                        bpy.ops.wm.call_menu(name="NODE_MT_context_menu")
                    else:
                        bpy.ops.wm.search_single_menu(
                            "INVOKE_DEFAULT", menu_idname="NODE_MT_add"
                        )
            else:
                try:
                    bpy.ops.wm.call_menu(name=self.menu_by_mode[context.mode])
                except RuntimeError:
                    bpy.ops.wm.call_panel(name=self.menu_by_mode[context.mode])
        else:
            if space_type == "VIEW_3D":
                bpy.ops.view3d.select("INVOKE_DEFAULT")

    def invoke(self, context, event):
        print(f"[INVOKE DEBUG] Called in {context.space_data.type}")
        
        # Reset state variables
        self._count = 0
        self._finished = False
        self._callMenu = False
        self._ortho = False
        self._back_to_ortho = False
        self._waiting_for_input = True  # Start in waiting state
        self._navigation_started = False
        self._focal_manager = FocalLengthManager()
        
        # Store Blender cursor position
        self.view_x = event.mouse_x
        self.view_y = event.mouse_y
        return self.execute(context)

    def execute(self, context):
        preferences = context.preferences
        addon_prefs = preferences.addons[__package__].preferences
        enable_nodes = addon_prefs.enable_for_node_editors

        space_type = context.space_data.type
        print(f"[EXECUTE DEBUG] space_type: {space_type}, enable_nodes: {enable_nodes}")

        # Start in waiting mode instead of immediately starting navigation
        if space_type == "VIEW_3D":
            # Don't store original focal length here - let the focal manager handle it
            # when navigation actually starts to avoid contamination from rapid activation
            
            # Use a higher frequency timer for more responsive auto-activation
            # 50 FPS = 0.02 seconds per tick for better responsiveness
            wm = context.window_manager
            self._timer = wm.event_timer_add(0.02, window=context.window)
            wm.modal_handler_add(self)
            print(f"[EXECUTE DEBUG] 3D View timer created: {self._timer}")
            return {"RUNNING_MODAL"}

        elif space_type == "NODE_EDITOR" and enable_nodes:
            # For node editor, use same timer frequency as 3D view for consistency
            wm = context.window_manager
            self._timer = wm.event_timer_add(0.02, window=context.window)
            wm.modal_handler_add(self)
            print(f"[EXECUTE DEBUG] Node Editor timer created: {self._timer}")
            return {"RUNNING_MODAL"}

        elif space_type == "IMAGE_EDITOR":
            bpy.ops.wm.call_panel(name="VIEW3D_PT_paint_texture_context_menu")
            return {"FINISHED"}
        
        print(f"[EXECUTE DEBUG] No conditions met, returning FINISHED")
        return {"FINISHED"}

    def _start_navigation(self, context):
        """Start walk/fly navigation mode and focal length transition"""
        preferences = context.preferences
        addon_prefs = preferences.addons[__package__].preferences
        disable_camera = addon_prefs.disable_camera_navigation
        
        view = context.space_data.region_3d.view_perspective
        
        if not (view == "CAMERA" and disable_camera):
            try:
                # Start focal length transition if enabled (original_lens is already stored)
                if self._focal_manager:
                    self._focal_manager.start_entry_transition(context, addon_prefs)
                
                bpy.ops.view3d.walk('INVOKE_DEFAULT')
                self._navigation_started = True
                self._waiting_for_input = False
                
                # Removed scheduling of nav key simulation
                
                # Check viewport mode for ortho restoration
                if bpy.context.region_data.is_perspective:
                    self._ortho = False
                else:
                    self._back_to_ortho = addon_prefs.return_to_ortho_on_exit
                
                return True
            except RuntimeError as e:
                print(f"[RMN DEBUG] RuntimeError in _start_navigation: {e}")
                self.report({"ERROR"}, "Cannot Navigate an Object with Constraints")
                return False
        else:
            print("[RMN DEBUG] Conditions for navigation NOT met (camera view or disabled).")
        return False

    def cancel(self, context):
        # Handle interrupted focal length transitions first - only in 3D viewport
        if self._focal_manager and context.space_data.type == "VIEW_3D":
            addon_prefs = context.preferences.addons[__package__].preferences
            if self._focal_manager.is_transitioning and not self._focal_manager.is_exit_transition:
                # Entry transition was interrupted, restore original immediately
                self._focal_manager.force_restore_original(context, addon_prefs)
        
        # Always check if exit transition is needed when canceling - only in 3D viewport
        if (self._focal_manager and context.space_data.type == "VIEW_3D" and
            (self._focal_manager.original_lens is not None or 
             FocalLengthManager._global_true_original_lens is not None) and
            self._focal_manager.should_change_focal_length(context.preferences.addons[__package__].preferences)):
            # Need exit transition - use higher frequency timer for smoother animation
            wm = context.window_manager
            if self._timer:
                wm.event_timer_remove(self._timer)
            # Use 60 FPS timer for smooth exit transition
            self._timer = wm.event_timer_add(0.016, window=context.window)
        else:
            # No exit transition needed - remove timer normally
            wm = context.window_manager
            if self._timer:
                wm.event_timer_remove(self._timer)
                self._timer = None