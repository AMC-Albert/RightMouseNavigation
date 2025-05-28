import bpy
import time


class FocalLengthManager:
    """Manages focal length transitions for walk/fly mode"""
    
    # Class variables to persist across instances
    _global_true_original_lens = None
    _global_walk_mode_session_active = False
    _last_activity_time = 0.0  # Track when last walk mode activity occurred
    _cleanup_delay = 1.0  # Seconds to wait before clearing global state
    
    def __init__(self):
        self.original_lens = None
        self.true_original_lens = None  # The real original before any transitions
        self.is_transitioning = False
        self.transition_start_time = 0.0
        self.transition_duration = 0.12  # Default fallback, will be overridden
        self.transition_initial_lens = None
        self.transition_target_lens = None
        self.is_exit_transition = False
        self.exit_transition_attempted = False
        self.walk_mode_ever_activated = False  # Track if walk mode was ever fully activated
        
        # Copy global state to instance
        self.true_original_lens = FocalLengthManager._global_true_original_lens
    
    def reset(self):
        """Reset all state variables"""
        self.original_lens = None
        self.true_original_lens = None
        self.is_transitioning = False
        self.transition_start_time = 0.0
        self.transition_initial_lens = None
        self.transition_target_lens = None
        self.is_exit_transition = False
        self.exit_transition_attempted = False
        self.walk_mode_ever_activated = False
    
    def should_change_focal_length(self, addon_prefs):
        """Check if focal length should be changed based on preferences"""
        walk_focal_length_enable = getattr(addon_prefs, "walk_mode_focal_length_enable", False)
        walk_focal_length = addon_prefs.walk_mode_focal_length
        return walk_focal_length_enable and walk_focal_length > 0
    
    def start_entry_transition(self, context, addon_prefs):
        """Start transition to walk mode focal length"""
        if not self.should_change_focal_length(addon_prefs):
            return
        
        FocalLengthManager._last_activity_time = time.time()
        walk_focal_length = addon_prefs.walk_mode_focal_length
        current_lens = context.space_data.lens
        
        # If no global session is active, this is a fresh start.
        # Capture the current lens as the true original for this new session.
        if not FocalLengthManager._global_walk_mode_session_active:
            FocalLengthManager._global_true_original_lens = current_lens
            # print(f"[FML Entry] New session. Captured global true original: {current_lens}")

        # Now, set the instance's original lens.
        # If _global_true_original_lens was set (either just now or from a continuing session), use it.
        if FocalLengthManager._global_true_original_lens is not None:
            self.true_original_lens = FocalLengthManager._global_true_original_lens
            self.original_lens = self.true_original_lens # Instance's original for this transition
            # print(f"[FML Entry] Using global true original for instance: {self.true_original_lens}")
        else:
            # This case implies _global_walk_mode_session_active was True,
            # but _global_true_original_lens was None, or _global_walk_mode_session_active was False
            # and _global_true_original_lens somehow didn't get set above.
            # This indicates an inconsistent state. To be safe, capture current_lens.
            self.true_original_lens = current_lens
            self.original_lens = current_lens
            FocalLengthManager._global_true_original_lens = current_lens # Ensure global is also updated
            # print(f"[FML Entry] Fallback/Inconsistent State: Captured global and instance original: {current_lens}")

        # Mark that a walk mode session is now active (or continues to be active)
        FocalLengthManager._global_walk_mode_session_active = True
        
        self.walk_mode_ever_activated = True
        self.exit_transition_attempted = False
        
        if abs(current_lens - walk_focal_length) > 0.001:
            # Check if transitions are disabled (duration = 0)
            if addon_prefs.walk_mode_transition_duration == 0:
                # Instant transition
                context.space_data.lens = walk_focal_length
                return
            
            self.transition_initial_lens = current_lens
            self.transition_target_lens = walk_focal_length
            self.is_transitioning = True
            self.is_exit_transition = False
            self.transition_start_time = time.time()
            # Use duration from preferences
            self.transition_duration = addon_prefs.walk_mode_transition_duration

    def start_exit_transition(self, context, addon_prefs):
        """Start transition back to original focal length"""
        # Update activity time
        FocalLengthManager._last_activity_time = time.time()
        
        # Prevent repeated attempts
        if self.exit_transition_attempted:
            return False
            
        self.exit_transition_attempted = True
        
        # Use true_original_lens if available, fallback to original_lens
        target_lens = self.true_original_lens if self.true_original_lens is not None else self.original_lens
        
        if not self.should_change_focal_length(addon_prefs) or target_lens is None:
            return False
        
        current_lens = context.space_data.lens
        
        if abs(current_lens - target_lens) > 0.001:
            # Check if transitions are disabled (duration = 0)
            if addon_prefs.walk_mode_transition_duration == 0:
                # Instant transition
                context.space_data.lens = target_lens
                self._cleanup_after_exit()
                return False  # No need to continue with modal updates
            
            self.transition_initial_lens = current_lens
            self.transition_target_lens = target_lens
            self.is_transitioning = True
            self.is_exit_transition = True
            self.transition_start_time = time.time()
            # Use duration from preferences
            self.transition_duration = addon_prefs.walk_mode_transition_duration
            return True
        else:
            # If lens is already at target, just cleanup
            self._cleanup_after_exit()
        
        return False
    
    def _cleanup_after_exit(self):
        """Clean up after successful exit transition"""
        self.original_lens = None
        self.true_original_lens = None
        self.walk_mode_ever_activated = False
        # Only clear global state when truly exiting - check if we're actually restoring to original
        # This prevents premature clearing during rapid activations
    
    def clear_global_state(self):
        """Explicitly clear global state - should only be called when completely done"""
        FocalLengthManager._global_true_original_lens = None
        FocalLengthManager._global_walk_mode_session_active = False
    
    def _should_clear_global_state(self):
        """Check if enough time has passed to safely clear global state"""
        if FocalLengthManager._last_activity_time == 0.0:
            return True  # No activity recorded, safe to clear
        
        time_since_activity = time.time() - FocalLengthManager._last_activity_time
        return time_since_activity >= FocalLengthManager._cleanup_delay
    
    def update_transition(self, context):
        """Update ongoing transition, returns True if transition completed"""
        if not self.is_transitioning:
            return False
        
        elapsed = time.time() - self.transition_start_time
        
        if (self.transition_initial_lens is None or 
            self.transition_target_lens is None):
            self.is_transitioning = False
            return True
        
        if elapsed >= self.transition_duration:
            # Transition complete
            context.space_data.lens = self.transition_target_lens
            
            # Force viewport update
            context.area.tag_redraw()
            
            # Store the exit transition state before clearing
            was_exit_transition = self.is_exit_transition
            
            self.is_transitioning = False
            self.is_exit_transition = False
            
            if was_exit_transition:
                # Clear all lens tracking after successful exit transition
                self._cleanup_after_exit()
            
            return True
        else:
            # Interpolate with easing for smoother transitions
            t = elapsed / self.transition_duration
            # Apply ease-out curve for smoother motion
            t = 1 - (1 - t) * (1 - t)
            new_lens = (self.transition_initial_lens + 
                       (self.transition_target_lens - self.transition_initial_lens) * t)
            context.space_data.lens = new_lens
            
            # Force viewport update for smooth visual feedback
            context.area.tag_redraw()
            
            return False
    
    def force_restore_original(self, context, addon_prefs):
        """Force restore to original focal length without transition"""
        # Use true_original_lens if available, fallback to original_lens
        target_lens = self.true_original_lens if self.true_original_lens is not None else self.original_lens
        
        if (target_lens is not None and 
            self.should_change_focal_length(addon_prefs) and
            context.space_data.type == "VIEW_3D"):
            context.space_data.lens = target_lens
            # DON'T cleanup here - we might need the original lens for proper exit later
            # Only stop any ongoing transition
            self.is_transitioning = False
    
    def cleanup(self, context, addon_prefs):
        """Final cleanup actions for the focal length manager"""
        # Always mark the session as inactive when cleanup is called,
        # as this signifies the end of the current operator's interaction.
        FocalLengthManager._global_walk_mode_session_active = False
        # print("[FML Cleanup] Session marked as inactive.")

        # If not transitioning and enough time has passed, clear global state for the lens value
        if not self.is_transitioning and self._should_clear_global_state():
            # print("[FML Cleanup] Clearing global true original lens due to inactivity.")
            # clear_global_state also sets _global_walk_mode_session_active to False, which is fine.
            self.clear_global_state()
        
        # Fallback: If an exit transition was attempted but didn't complete,
        # and we're not currently transitioning, force restore.
        # This handles cases where the modal operator might terminate abruptly.
        elif self.exit_transition_attempted and not self.is_transitioning:
            if self.true_original_lens is not None and self.should_change_focal_length(addon_prefs):
                # print("[FML Cleanup] Forcing restore due to incomplete exit transition.")
                self.force_restore_original(context, addon_prefs)
            # print("[FML Cleanup] Clearing global state after forced restore.")
            self.clear_global_state() # Ensure global state is cleared after forced restore
